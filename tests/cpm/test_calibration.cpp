// Reuse the real-ASN.1 fixtures and actual CpmChecks entry point from A3.
#define main a3_fixture_main
#include "test_a3.cpp"
#undef main
int main() {
    try {
        const Milliseconds t=448538400500LL;
        Json sensitivity=Json::array();
        const double candidates[][4]={{1.6,4.6,90,3},{3,4.5,90,3},{3,4.5,90,4},
            {3,4.5,120,4},{3,4.5,180,4},{6,6,120,4},{10,10,360,10}};
        for(const auto& q:candidates) {
            auto p=parameters(); p.MAX_PLAUSIBLE_ACCEL=q[0]; p.MAX_PLAUSIBLE_DECEL=q[1];
            p.MAX_PLAUSIBLE_ANGLE_CHANGE=q[2]; p.TOLERANCE_EXCEED_SPEED=q[3];
            Engine acceleration; actual(acceleration,message(t),t,101,p);
            auto a=actual(acceleration,message(t+100,2000),t+100,101,p);
            check(row(a,"speed_consistency")["status"]=="anomaly","obvious acceleration still detected under every candidate");
            check(row(a,"speed_plausibility")["status"]=="passed","temporal test independent of A2 speed alarm");
            Engine deceleration; actual(deceleration,message(t,2000),t,101,p);
            auto d=actual(deceleration,message(t+100,100),t+100,101,p);
            check(row(d,"speed_consistency")["status"]=="anomaly","obvious deceleration retained");
            Engine direction; actual(direction,message(t,1000,0),t,101,p);
            auto b=actual(direction,message(t+100,0,1000),t+100,101,p);
            check(row(b,"direction_consistency")["status"]=="anomaly","90degree change in100ms retained");
            Engine position; actual(position,message(t),t,101,p);
            auto c=actual(position,message(t+100,100,0,2000),t+100,101,p);
            check(row(c,"position_speed_consistency")["status"]=="anomaly","20m jump in100ms retained");
            Engine healthy; actual(healthy,message(t,-100),t,101,p);
            auto h=actual(healthy,message(t+100,-115,0,-10),t+100,101,p);
            check(h["anomalies"]==0,"signed 1.5m/s2 consistent fixture remains evaluable and passes");
            sensitivity.push_back({{"acceleration",q[0]},{"deceleration",q[1]},{"direction",q[2]},{"position_tolerance",q[3]},
                {"large_acceleration_detected",true},{"large_deceleration_detected",true},{"large_turn_detected",true},{"large_jump_detected",true}});
        }
        Engine repeated; actual(repeated,message(t),t);
        auto first=actual(repeated,message(t+100,2000),t+100);
        check(row(first,"speed_consistency")["status"]=="anomaly","first rejected observation really evaluated");
        const auto accepted=repeated.history.begin()->second.sample.measurement_ms;
        auto copy=message(t+200,2000); object(copy).measurementDeltaTime=-200;
        auto duplicate=actual(repeated,copy,t+200);
        check(row(duplicate,"temporal_order")["reason"]=="repeated measurement","retransmitted rejected observation recognized");
        check(row(duplicate,"speed_consistency")["status"]=="non_evaluable","retransmission does not duplicate anomaly");
        check(repeated.history.begin()->second.sample.measurement_ms==accepted,"observed cache never becomes accepted baseline");
        auto conflict=copy; object(conflict).velocity->choice.cartesianVelocity.xVelocity.value=2100;
        auto conflicting=actual(repeated,conflict,t+201);
        check(row(conflicting,"temporal_order")["reason"]=="conflicting repeated measurement","conflict at rejected timestamp explicit");
        actual(repeated,message(t+200,100,0,0,0,9),t+202);
        duplicate=actual(repeated,copy,t+203);
        check(row(duplicate,"speed_consistency")["status"]=="non_evaluable","cache handles intervening object");
        auto recovered=actual(repeated,message(t+300),t+300);
        check(row(recovered,"speed_consistency")["dt_s"]==.3,"recovery still uses last trusted state");
        actual(repeated,message(t+17000),t+17000);
        check(repeated.observations.size()==1,"expired observation cache is purged");
        Engine invalid; actual(invalid,message(t),t); const auto size=invalid.observations.size();
        auto future=message(t+100); object(future).measurementDeltaTime=100;
        actual(invalid,future,t+100);
        check(invalid.observations.size()==size,"future measure cannot poison observation cache");
        Context context; context.receiver=101; context.receive_ms=t+200; context.engine=&invalid;
        auto converted=prepare(message(t+200),context); bool error=false;
        try {invalid.evaluate(context.message,101,t+200,context.policy,[](double,double)->double {throw std::runtime_error("technical callback");});}
        catch(const std::exception&) {error=true;}
        check(error && invalid.observations.size()==size,"technical failure rolls back observation cache");
        std::cout<<Json({{"passed",true},{"assertions",assertions},{"actual_f2md",true},{"candidate_sensitivity",sensitivity}}).dump()<<std::endl;
    }catch(const std::exception& e) {std::cerr<<"Calibration test failed after "<<assertions<<": "<<e.what()<<std::endl; return 1;}
}
