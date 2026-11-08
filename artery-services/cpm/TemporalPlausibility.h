#pragma once
// Internal R2 temporal model. No ASN.1 narrowing, OMNeT globals, or Kalman state.
#include <nlohmann/json.hpp>
#include <array>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace artery { namespace cpm_a3 {
using Json=nlohmann::json;
using Milliseconds=std::int64_t;
struct Object {
    std::optional<std::uint16_t> id;
    Milliseconds measurement_ms=0, delta_ms=0;
    long x_cm=0,y_cm=0,vx_cm_s=0,vy_cm_s=0;
    bool position_available=false,velocity_available=false;
    // The local ENU origin belongs to this measurement, not the receiver pose.
    std::optional<double> latitude_deg,longitude_deg;
};
struct Message { std::uint32_t station=0; Milliseconds reference_ms=0; std::vector<Object> objects; };
struct Policy {
    Milliseconds maximum_age_ms=5000,expiration_ms=15000,maximum_interval_ms=5000;
    double acceleration_m_s2=3, deceleration_m_s2=4.5,angular_rate_deg_s=90;
    double excess_speed_m_s=4;
    // Quantisation only, NOT a calibrated sensor uncertainty.
    double velocity_quantisation_m_s=std::sqrt(2.)*.005;
    double position_quantisation_m=.05; // two cm-grid points + two 1e-7 degree origins
};
class Engine {
public:
    using Key=std::tuple<std::uint64_t,std::uint32_t,std::uint16_t>;
    struct Entry { Object sample; Milliseconds accepted_rx_ms; };
    std::map<Key,Entry> history;
    // Observed is NOT trusted history. A rejected measurement must not become
    // a baseline, but retransmitting it must not create another temporal alarm.
    using ObservationKey=std::tuple<std::uint64_t,std::uint32_t,std::uint16_t,Milliseconds>;
    std::map<ObservationKey,Entry> observations;
    std::map<std::uint64_t,Milliseconds> receiver_clock;
    static constexpr double pi=3.14159265358979323846;
    static double norm(long x,long y) { return std::hypot(double(x),double(y))/100.; }
    static bool identical(const Object& a,const Object& b) {
        return a.measurement_ms==b.measurement_ms && a.delta_ms<=0 && b.delta_ms<=0 &&
            a.position_available==b.position_available && a.velocity_available==b.velocity_available &&
            a.x_cm==b.x_cm && a.y_cm==b.y_cm && a.vx_cm_s==b.vx_cm_s && a.vy_cm_s==b.vy_cm_s &&
            a.latitude_deg==b.latitude_deg && a.longitude_deg==b.longitude_deg;
    }
    static std::array<double,3> east(double lon) { return {-std::sin(lon),std::cos(lon),0}; }
    static std::array<double,3> north(double lat,double lon) { return {-std::sin(lat)*std::cos(lon),-std::sin(lat)*std::sin(lon),std::cos(lat)}; }
    static std::array<double,3> surface(double lat,double lon) {
        const double a=6378137.,e2=6.69437999014e-3,n=a/std::sqrt(1-e2*std::sin(lat)*std::sin(lat));
        return {n*std::cos(lat)*std::cos(lon),n*std::cos(lat)*std::sin(lon),n*(1-e2)*std::sin(lat)};
    }
    static std::optional<double> displacement(const Object& old,const Object& current) {
        if(!old.position_available || !current.position_available || !old.latitude_deg || !old.longitude_deg ||
            !current.latitude_deg || !current.longitude_deg) return {};
        const double lat=*old.latitude_deg*pi/180,lon=*old.longitude_deg*pi/180;
        const double lat2=*current.latitude_deg*pi/180,lon2=*current.longitude_deg*pi/180;
        const auto a=surface(lat,lon),b=surface(lat2,lon2),e=east(lon),n=north(lat,lon),e2=east(lon2),n2=north(lat2,lon2);
        double dx=0,dy=0,origin2=0;
        for(int k=0;k<3;++k) {
            const double origin=b[k]-a[k]; origin2+=origin*origin;
            const double d=origin+e2[k]*current.x_cm/100.+n2[k]*current.y_cm/100.-e[k]*old.x_cm/100.-n[k]*old.y_cm/100.;
            dx+=e[k]*d; dy+=n[k]*d;
        }
        if(origin2>500.*500.) return {}; // bounded horizontal approximation, no invented altitude
        return std::hypot(dx,dy);
    }
    Json evaluate(const Message& msg,std::uint64_t receiver,Milliseconds now,const Policy& p,
                  const std::function<double(double,double)>& speed) {
        if(now<0 || msg.reference_ms<0 || p.maximum_age_ms<=0 || p.expiration_ms<=0 || p.maximum_interval_ms<=0 ||
            !std::isfinite(p.acceleration_m_s2) || p.acceleration_m_s2<0 || !std::isfinite(p.deceleration_m_s2) || p.deceleration_m_s2<0 ||
            !std::isfinite(p.angular_rate_deg_s) || p.angular_rate_deg_s<0 || !std::isfinite(p.excess_speed_m_s) || p.excess_speed_m_s<0)
            throw std::runtime_error("invalid A3 clock/policy");
        const auto clock=receiver_clock.find(receiver);
        if(clock!=receiver_clock.end() && now<clock->second) throw std::runtime_error("receiver clock regressed");
        // Transaction: any technical exception rolls back the complete message.
        auto next=history;
        auto nextObservations=observations;
        Json expired=Json::array(),results=Json::array(),states=Json::array();
        for(auto i=next.begin();i!=next.end();) {
            if(std::get<0>(i->first)==receiver && now-i->second.accepted_rx_ms>p.expiration_ms) {
                expired.push_back({{"station",std::get<1>(i->first)},{"id",std::get<2>(i->first)}}); i=next.erase(i);
            } else ++i;
        }
        for(auto i=nextObservations.begin();i!=nextObservations.end();) {
            if(std::get<0>(i->first)==receiver && now-i->second.accepted_rx_ms>p.expiration_ms) i=nextObservations.erase(i);
            else ++i;
        }
        std::map<std::uint16_t,bool> seen;
        for(const auto& object:msg.objects) if(object.id && !seen.emplace(*object.id,true).second)
            throw std::runtime_error("duplicate R2 object ID in one message");
        for(const auto& object:msg.objects) {
            const Json id=object.id?Json(*object.id):Json(nullptr);
            Json state={{"id",id},{"measurement_time_ms",object.measurement_ms},{"measurement_delta_ms",object.delta_ms},
                {"history_action","rejected"}};
            auto record=[&](const char* name,const char* status,const std::string& reason,Json detail=Json::object()) {
                detail["id"]=id; detail["check"]=name; detail["status"]=status; detail["reason"]=reason;
                detail["measurement_time_ms"]=object.measurement_ms; results.push_back(detail);
            };
            bool anomaly=false;
            if(object.velocity_available) {
                const double value=speed(object.vx_cm_s,object.vy_cm_s); // unchanged real F2MD XY check, cm/s
                if(!std::isfinite(value) || (value!=0 && value!=1)) throw std::runtime_error("invalid F2MD speed result");
                anomaly=value>0;
                record("speed_plausibility",anomaly?"anomaly":"passed","A2 XY control unchanged",{{"result",value}});
            } else record("speed_plausibility","non_evaluable","velocity unavailable");
            auto reject=[&](const std::string& why) {
                record("temporal_order","non_evaluable",why);
                for(const char* name:{"speed_consistency","direction_consistency","position_speed_consistency"}) record(name,"non_evaluable",why);
                state["reason"]=why; states.push_back(state);
            };
            if(!object.id) { reject("object ID absent; no ID invented"); continue; }
            if(object.measurement_ms<0 || object.delta_ms>0 || object.measurement_ms>msg.reference_ms || msg.reference_ms>now || object.measurement_ms>now) {
                reject("future or invalid message/measurement timestamp"); continue;
            }
            if(now-object.measurement_ms>p.maximum_age_ms || now-msg.reference_ms>p.maximum_age_ms) {
                reject("stale measurement/message"); continue;
            }
            const Key key(receiver,msg.station,*object.id);
            const ObservationKey seenKey(receiver,msg.station,*object.id,object.measurement_ms);
            const auto seen=nextObservations.find(seenKey);
            if(seen!=nextObservations.end()) {
                reject(identical(object,seen->second.sample)?"repeated measurement":"conflicting repeated measurement");
                continue;
            }
            nextObservations.emplace(seenKey,Entry{object,now});
            auto prior=next.find(key);
            if(prior!=next.end() && object.measurement_ms<=prior->second.sample.measurement_ms) {
                reject(object.measurement_ms<prior->second.sample.measurement_ms?"out_of_order measurement":
                    (identical(object,prior->second.sample)?"repeated measurement":"conflicting repeated measurement")); continue;
            }
            record("temporal_order","passed","full 64-bit measurement time accepted",{{"age_ms",now-object.measurement_ms}});
            const bool initialized=prior!=next.end();
            const Milliseconds dt_ms=initialized?object.measurement_ms-prior->second.sample.measurement_ms:0;
            if(!initialized || dt_ms>p.maximum_interval_ms) {
                const std::string why=initialized?"measurement gap expired; new baseline":"no valid history; initialization";
                for(const char* name:{"speed_consistency","direction_consistency","position_speed_consistency"}) record(name,"non_evaluable",why);
                state["history_action"]=anomaly?"rejected":"initialized";
                if(!anomaly) next[key]={object,now};
            } else {
                const auto& old=prior->second.sample;
                const double dt=double(dt_ms)/1000.;
                state["previous_measurement_time_ms"]=old.measurement_ms; state["dt_ms"]=dt_ms; state["dt_s"]=dt;
                if(!object.velocity_available || !old.velocity_available) {
                    for(const char* name:{"speed_consistency","direction_consistency","position_speed_consistency"}) record(name,"non_evaluable","current/previous velocity unavailable",{{"dt_s",dt}});
                } else {
                    const double before=norm(old.vx_cm_s,old.vy_cm_s),after=norm(object.vx_cm_s,object.vy_cm_s);
                    const double difference=after-before;
                    const double allowance=(difference>=0?p.acceleration_m_s2:p.deceleration_m_s2)*dt+2*p.velocity_quantisation_m_s;
                    const bool failed=std::abs(difference)>allowance;
                    record("speed_consistency",failed?"anomaly":"passed","scalar ground-speed change with quantisation allowance",
                        {{"dt_s",dt},{"previous_speed_m_s",before},{"speed_m_s",after},{"speed_change_m_s",difference},{"allowed_change_m_s",allowance}});
                    anomaly|=failed;
                    if(before<=.2 || after<=.2) record("direction_consistency","non_evaluable","direction undefined at near-zero speed",{{"dt_s",dt}});
                    else {
                        const double a=std::atan2(double(old.vy_cm_s),double(old.vx_cm_s));
                        const double b=std::atan2(double(object.vy_cm_s),double(object.vx_cm_s));
                        const double turn=std::abs(std::remainder(b-a,2*pi))*180/pi;
                        const double allowed=p.angular_rate_deg_s*dt+
                            (std::asin(std::min(1.,p.velocity_quantisation_m_s/before))+std::asin(std::min(1.,p.velocity_quantisation_m_s/after)))*180/pi;
                        const bool bad=turn>allowed;
                        record("direction_consistency",bad?"anomaly":"passed","XY directions in degrees; shortest angular difference",
                            {{"dt_s",dt},{"angle_change_deg",turn},{"allowed_change_deg",allowed}}); anomaly|=bad;
                    }
                    auto distance=displacement(old,object);
                    if(!distance) record("position_speed_consistency","non_evaluable","position/geographic origin unavailable or origin separation >500m",{{"dt_s",dt}});
                    else {
                        const double bound=(std::max(before,after)+p.excess_speed_m_s)*dt+p.position_quantisation_m;
                        const bool bad=*distance>bound;
                        record("position_speed_consistency",bad?"anomaly":"passed","horizontal WGS84 origin motion + ENU, metres and seconds",
                            {{"dt_s",dt},{"displacement_m",*distance},{"allowed_distance_m",bound}}); anomaly|=bad;
                    }
                }
                state["history_action"]=anomaly?"rejected":"updated";
                if(!anomaly) next[key]={object,now};
            }
            states.push_back(state);
        }
        for(const char* name:{"distance_plausibility","kalman_consistency"})
            results.push_back({{"check",name},{"status","non_evaluable"},{"reason","disabled: frame/sensor/confidence contract not validated"}});
        if(next.size()>65536) throw std::runtime_error("A3 history capacity exceeded");
        if(nextObservations.size()>131072) throw std::runtime_error("A3 observation cache capacity exceeded");
        Json evaluated=Json::array(),skipped=Json::array(); int anomalies=0;
        for(const auto& row:results) {
            if(row["status"]=="non_evaluable") skipped.push_back(row);
            else { evaluated.push_back(row); anomalies+=row["status"]=="anomaly"; }
        }
        Json result={{"checks",results},{"evaluated",evaluated},{"non_evaluable",skipped},{"history",states},{"expired",expired},
            {"anomalies",anomalies},{"complete",false},{"receiver",receiver},{"station",msg.station},
            {"reference_time_ms",msg.reference_ms},{"receive_time_ms",now},
            {"verdict",anomalies?"anomaly":(evaluated.empty()?"non_evaluable":"partial")},
            {"scope","evaluated_checks_only; never a global healthy verdict"},
            {"policy",{{"acceleration_m_s2",p.acceleration_m_s2},{"deceleration_m_s2",p.deceleration_m_s2},
                {"angular_rate_deg_s",p.angular_rate_deg_s},{"excess_speed_m_s",p.excess_speed_m_s},
                {"maximum_age_ms",p.maximum_age_ms},{"expiration_ms",p.expiration_ms},{"maximum_interval_ms",p.maximum_interval_ms}}}};
        history.swap(next); observations.swap(nextObservations); receiver_clock[receiver]=now;
        return result;
    }
};
struct Context {
    Engine* engine=nullptr;
    Message message;
    std::uint64_t receiver=0;
    Milliseconds receive_ms=0;
    Policy policy;
    bool facility_called=false,checks_called=false;
};
}} // namespace artery::cpm_a3
