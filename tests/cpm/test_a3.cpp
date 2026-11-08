#include "artery-services/cpm/R2Temporal.h"
#include "artery/application/F2MD/mdFiles/mdChecks/CpmChecks.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace artery::cpm_a3;
namespace a2=artery::cpm_a2;
int assertions=0;
void check(bool ok,const char* reason) { if(!ok) throw std::runtime_error(reason); ++assertions; }
Json row(const Json& result,const std::string& name,int id=7) {
    for(const auto& r:result.at("checks")) if(r.at("check")==name && r.contains("id") && r["id"]==id) return r;
    throw std::runtime_error("check missing: "+name);
}
F2MD_CPParameters parameters() {
    F2MD_CPParameters p; p.MAX_PLAUSIBLE_SPEED=70; p.MAX_PLAUSIBLE_ACCEL=3; p.MAX_PLAUSIBLE_DECEL=4.5;
    p.MAX_PLAUSIBLE_ANGLE_CHANGE=90; p.TOLERANCE_EXCEED_SPEED=4; p.MAX_CPM_DELTATIME=5; p.MAX_CPM_HISTORY_TIME=15; return p;
}
Json actual(Engine& engine,vanetza::asn1::r2::Cpm r2,Milliseconds now,std::uint64_t receiver=101,F2MD_CPParameters p=parameters()) {
    CpmChecks checks(&p); CpmCheckList list; list.resetAll();
    Context context; context.engine=&engine; context.receiver=receiver; context.receive_ms=now;
    auto decoded=a2::decode(r2.encode()); auto converted=prepare(decoded,context); a2::Scope scope(converted);
    checks.CpmChecksum(converted.legacy,nullptr,list,nullptr);
    check(context.checks_called,"real F2MD CpmChecksum A3 branch not reached");
    return converted.control;
}
vanetza::asn1::r2::Cpm message(Milliseconds time,long vx=100,long vy=0,long x=0,long y=0,int id=7,std::uint32_t station=88) {
    Json snapshot={{"schema_version",2},{"frame","ENU"},{"velocity_frame","ground_ENU"},
        {"time_base","sumo_simulation_seconds"},{"frame_id",42},{"measurement_time_s",.4},
        {"reference",{{"latitude",50.3},{"longitude",3.5},{"heading_deg",90}}},
        {"objects",Json::array({{{"track_id",id},{"x",x/100.},{"y",y/100.},{"vx",vx/100.},{"vy",vy/100.},{"class","Car"}}})}};
    return artery::perception::build(snapshot,station,time,.5);
}
Vanetza_ITS2_PerceivedObject_t& object(vanetza::asn1::r2::Cpm& m) {
    return *m->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list.array[0];
}
int main(int argc,char** argv) {
    try {
        if(argc==3) {
            std::ifstream f(argv[1]); Json entries; f>>entries; Engine engine; Json out=Json::array();
            for(const auto& entry:entries) {
                std::ifstream input(entry.at("path").get<std::string>(),std::ios::binary);
                vanetza::ByteBuffer bytes((std::istreambuf_iterator<char>(input)),{});
                auto r2=a2::decode(bytes); auto p=parameters();
                if(entry.contains("parameters")) {
                    auto q=entry["parameters"];
                    p.MAX_PLAUSIBLE_SPEED=q.value("speed_limit_m_s",70.);
                    p.MAX_PLAUSIBLE_ACCEL=q.at("acceleration_m_s2"); p.MAX_PLAUSIBLE_DECEL=q.at("deceleration_m_s2");
                    p.MAX_PLAUSIBLE_ANGLE_CHANGE=q.at("angular_rate_deg_s"); p.TOLERANCE_EXCEED_SPEED=q.at("excess_speed_m_s");
                    p.MAX_CPM_DELTATIME=q.at("maximum_age_ms").get<double>()/1000.;
                    p.MAX_CPM_HISTORY_TIME=q.at("expiration_ms").get<double>()/1000.;
                }
                Json result;
                try {result=actual(engine,r2,entry.at("receive_time_ms"),entry.at("receiver"),p);}
                catch(const std::exception& e) { result={{"verdict","technical_error"},{"reason",e.what()}}; }
                out.push_back({{"provenance",entry},{"control",result}});
            }
            std::ofstream(argv[2])<<out.dump(2); return 0;
        }
        const Milliseconds t=448538400500LL;
        Engine one; auto r=actual(one,message(t),t);
        check(row(r,"speed_consistency")["status"]=="non_evaluable","initialization not a temporal pass");
        check(one.history.size()==1,"initialized history");
        r=actual(one,message(t+1),t+1);
        check(row(r,"speed_consistency")["dt_s"]==.001,"1ms floating dt");
        check(row(r,"speed_consistency")["status"]=="passed","1ms constant speed passes");
        r=actual(one,message(t+101,101,0,10),t+101);
        check(row(r,"speed_consistency")["dt_s"]==.1,"100ms floating dt");
        check(row(r,"speed_consistency")["status"]=="passed","physical acceleration at 100ms");
        Engine wrap; const auto base=t-t%65536;
        actual(wrap,message(base+65530),base+65530);
        r=actual(wrap,message(base+65630),base+65630);
        check(row(r,"speed_consistency")["dt_s"]==.1,"modulo rollover uses full time");
        check(r["reference_time_ms"]==base+65630,"full epoch not modulo");
        Engine multi;
        actual(multi,message(t,100,0,0,0,65535,4294967295U),t,101);
        actual(multi,message(t,100,0,0,0,65535,4294967295U),t,102);
        actual(multi,message(t,100,0,0,0,65535,89),t,101);
        actual(multi,message(t,100,0,0,0,256,88),t,101);
        check(multi.history.size()==4,"distinct receiver/station/full16bit-ID histories");
        check(multi.history.count(Engine::Key(101,4294967295U,65535))==1,"uint32 station and uint16 ID exact");
        r=actual(multi,message(t+100,100,0,0,0,65535,4294967295U),t+100,101);
        check(row(r,"speed_consistency",65535)["status"]=="passed","ID65535 temporal control");
        Engine reorder; auto m=message(t); auto second=message(t,200,0,0,0,9);
        auto& l=m->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer;
        auto* copied=vanetza::asn1::allocate<Vanetza_ITS2_PerceivedObject_t>();
        // Clone the second ASN.1 object via an independent CPM, then transfer ownership.
        auto& ll=second->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer;
        vanetza::asn1::free(asn_DEF_Vanetza_ITS2_PerceivedObject,copied);
        copied=ll.perceivedObjects.list.array[0]; ll.perceivedObjects.list.count=0;
        ASN_SEQUENCE_ADD(&l.perceivedObjects.list,copied); l.numberOfPerceivedObjects=2;
        actual(reorder,m,t); std::swap(l.perceivedObjects.list.array[0],l.perceivedObjects.list.array[1]);
        asn_long2INTEGER(&m->payload.managementContainer.referenceTime,t+100);
        r=actual(reorder,m,t+100);
        check(row(r,"speed_consistency",7)["status"]=="passed" && row(r,"speed_consistency",9)["status"]=="passed","reordered list not history index");
        Engine missingInLatest; actual(missingInLatest,message(t),t); actual(missingInLatest,message(t+50,100,0,0,0,9),t+50);
        r=actual(missingInLatest,message(t+100),t+100);
        check(row(r,"speed_consistency")["dt_s"]==.1,"object absent in latest CPM keeps own history");
        const auto accepted=one.history.begin()->second.sample.measurement_ms;
        r=actual(one,message(t+101,101,0,10),t+102);
        check(row(r,"temporal_order")["reason"]=="repeated measurement","duplicate measurement recognized");
        r=actual(one,message(t+101,102,0,10),t+103);
        check(row(r,"temporal_order")["reason"]=="conflicting repeated measurement","conflicting duplicate rejected");
        r=actual(one,message(t+50),t+104);
        check(row(r,"temporal_order")["reason"]=="out_of_order measurement","regressive measurement rejected");
        auto future=message(t+150); object(future).measurementDeltaTime=1;
        r=actual(one,future,t+150);
        check(row(r,"temporal_order")["status"]=="non_evaluable","future delta never anomaly");
        r=actual(one,message(t+200),t+151);
        check(row(r,"temporal_order")["status"]=="non_evaluable","future reference rejected");
        check(one.history.begin()->second.sample.measurement_ms==accepted,"rejected ordering never corrupts baseline");
        r=actual(one,message(t+102),t+7000);
        check(row(r,"temporal_order")["reason"]=="stale measurement/message","old measure rejected");
        r=actual(one,message(t+17000),t+17000);
        check(r["expired"].size()==1 && r["history"][0]["history_action"]=="initialized","expired history erased and initialized");
        Engine gap; actual(gap,message(t),t); r=actual(gap,message(t+6000),t+6000);
        check(row(r,"speed_consistency")["reason"]=="measurement gap expired; new baseline","gap expires comparison separately from retention");
        Engine missing; auto noV=message(t);
        auto& nv=object(noV); vanetza::asn1::free(asn_DEF_Vanetza_ITS2_Velocity3dWithConfidence,nv.velocity); nv.velocity=nullptr;
        r=actual(missing,noV,t);
        check(row(r,"speed_plausibility")["status"]=="non_evaluable","absent speed not zero");
        r=actual(missing,message(t+100),t+100);
        check(row(r,"speed_consistency")["status"]=="non_evaluable","previous speed missing");
        auto noId=message(t+200); auto& ni=object(noId); free(ni.objectId); ni.objectId=nullptr;
        r=actual(missing,noId,t+200);
        check(r["history"][0]["id"].is_null() && missing.history.size()==1,"no invented ID/history entry");
        Engine kinematics; actual(kinematics,message(t),t);
        r=actual(kinematics,message(t+100,1000),t+100);
        check(row(r,"speed_consistency")["status"]=="anomaly","acceleration anomaly detected by real F2MD branch");
        check(kinematics.history.begin()->second.sample.measurement_ms==t-100,"physical rejection keeps valid measurement");
        r=actual(kinematics,message(t+200,100,0,20),t+200);
        check(row(r,"speed_consistency")["dt_s"]==.2,"recovery compares last accepted state");
        Engine lateral; actual(lateral,message(t,-100,100),t);
        r=actual(lateral,message(t+100,-100,100,-10,10),t+100);
        check(row(r,"speed_consistency")["status"]=="passed" && row(r,"direction_consistency")["status"]=="passed","signed lateral XY not magnitude/angle");
        check(row(r,"position_speed_consistency")["status"]=="passed","metres displacement bound");
        Engine jump; actual(jump,message(t),t); r=actual(jump,message(t+100,100,0,1000),t+100);
        check(row(r,"position_speed_consistency")["status"]=="anomaly","position jump at100ms");
        Engine origins; auto old=message(t),moved=message(t+100,100,0,-100,0);
        auto& ref=moved->payload.managementContainer.referencePosition;
        ref.longitude+=140; // moving origin compensated by local X, about 1m at50deg
        actual(origins,old,t); r=actual(origins,moved,t+100);
        check(row(r,"position_speed_consistency")["status"]=="passed","moving sender origin compensated");
        Engine turn; actual(turn,message(t,1000,0),t);
        r=actual(turn,message(t+100,0,1000),t+100);
        check(row(r,"direction_consistency")["status"]=="anomaly","90degree turn in100ms exceeds90degree/s");
        check(turn.history.begin()->second.sample.measurement_ms==t-100,"rejected direction cannot replace baseline");
        Engine decel; actual(decel,message(t,1000),t);
        r=actual(decel,message(t+100,950),t+100);
        check(row(r,"speed_consistency")["status"]=="anomaly","deceleration threshold in m/s2 with floating dt");
        Engine angularWrap; actual(angularWrap,message(t,-1000,1),t);
        r=actual(angularWrap,message(t+100,-1000,-1),t+100);
        check(row(r,"direction_consistency")["status"]=="passed","angular wrap uses shortest difference");
        Engine unreferenced; auto unavailable=message(t);
        unavailable->payload.managementContainer.referencePosition.latitude=900000001;
        actual(unreferenced,unavailable,t);
        asn_long2INTEGER(&unavailable->payload.managementContainer.referenceTime,t+100);
        r=actual(unreferenced,unavailable,t+100);
        check(row(r,"speed_consistency")["status"]=="passed" && row(r,"position_speed_consistency")["status"]=="non_evaluable","missing origin skips only positional check");
        Engine fullDelta; auto veryOld=message(t); object(veryOld).measurementDeltaTime=-1600;
        r=actual(fullDelta,veryOld,t);
        check(r["history"][0]["measurement_time_ms"]==t-1600,"R2 delta outside R1 range kept signed");
        check(fullDelta.history.size()==1,"no legacy narrowing on delta");
        Engine blank; auto noTrack=message(t); free(object(noTrack).objectId); object(noTrack).objectId=nullptr;
        auto& vel=object(noTrack).velocity; vanetza::asn1::free(asn_DEF_Vanetza_ITS2_Velocity3dWithConfidence,vel); vel=nullptr;
        r=actual(blank,noTrack,t);
        check(r["verdict"]=="non_evaluable" && blank.history.empty(),"no speed and no ID never healthy");
        Engine refreshed; actual(refreshed,message(t),t); actual(refreshed,message(t),t+14000);
        r=actual(refreshed,message(t+16000),t+16000);
        check(r["expired"].size()==1,"rejected replay cannot extend expiration");
        Engine technical; actual(technical,message(t),t);
        bool thrown=false; try { actual(technical,message(t+100),t-1); } catch(const std::exception&) {thrown=true;}
        check(thrown && technical.history.begin()->second.sample.measurement_ms==t-100,"receiver regression technical error rolls back");
        Context context; context.engine=&technical; context.receiver=101; context.receive_ms=t+100;
        auto c=prepare(message(t+100),context);
        thrown=false; try {technical.evaluate(context.message,101,t+100,context.policy,[](double,double)->double {throw std::runtime_error("injected technical failure");});}catch(const std::exception&) {thrown=true;}
        check(thrown && technical.history.begin()->second.sample.measurement_ms==t-100,"check exception propagates and rolls back");
        auto p=parameters(); p.MAX_CPM_DELTATIME=-1; thrown=false;
        try { actual(technical,message(t+100),t+100,101,p); }catch(const std::exception&){thrown=true;}
        check(thrown,"invalid policy technical error");
        Engine transaction; Context batch; batch.receiver=101; batch.receive_ms=t; batch.engine=&transaction;
        auto two=prepare(m,batch); batch.message.reference_ms=t;
        for(auto& o:batch.message.objects) {o.measurement_ms=t-100; o.delta_ms=-100;}
        int calls=0; thrown=false;
        try {transaction.evaluate(batch.message,101,t,batch.policy,[&](double,double)->double {if(++calls==2) throw std::runtime_error("second object failure"); return 0;});}
        catch(const std::exception&){thrown=true;}
        check(thrown && transaction.history.empty() && transaction.receiver_clock.empty(),"technical failure rolls back prior objects in same message");
        thrown=false;
        try {transaction.evaluate(batch.message,101,t,batch.policy,[](double,double){return std::nan("");});}catch(const std::exception&){thrown=true;}
        check(thrown && transaction.history.empty(),"nonfinite real check result technical not anomaly");
        batch.message.objects[1].id=batch.message.objects[0].id; thrown=false;
        try {transaction.evaluate(batch.message,101,t,batch.policy,[](double,double){return 0;});}catch(const std::exception&){thrown=true;}
        check(thrown && transaction.history.empty(),"duplicate IDs cannot contaminate history");
        Engine speedRegression; r=actual(speedRegression,message(t,0,10000),t);
        check(row(r,"speed_plausibility")["status"]=="anomaly","unchanged70m/s lateral speed control");
        check(speedRegression.history.empty(),"initial implausible velocity not baseline");
        check(r["complete"]==false && row(r,"speed_consistency")["status"]=="non_evaluable","partial never complete healthy verdict");
        auto encoded=message(t).encode(); encoded.resize(5); thrown=false;
        try {a2::decode(encoded);}catch(const std::exception&){thrown=true;}
        check(thrown,"real Vanetza truncated decode error");
        const long old100=100/1e3,old1=1/1e3,oldWrap=(94-65530)/1e3;
        check(old100==0 && old1==0 && oldWrap==-65,"compiled reproduction of original truncation/wrap defects");
        std::cout<<Json({{"passed",true},{"assertions",assertions},{"actual_f2md",true},{"real_vanetza_roundtrips",true},
            {"numeric_examples",{{"100ms_before_s",old100},{"100ms_after_s",.1},{"1ms_before_s",old1},{"1ms_after_s",.001},
                {"wrap_before_s",oldWrap},{"wrap_after_s",.1}}}}).dump()<<std::endl;
    } catch(const std::exception& e) {std::cerr<<"A3 test failure after "<<assertions<<" assertions: "<<e.what()<<std::endl; return 1;}
}
