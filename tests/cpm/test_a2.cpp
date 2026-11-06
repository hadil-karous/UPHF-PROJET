#include "artery-services/cpm/R2ToLegacy.h"
#include "artery/application/F2MD/mdFiles/mdChecks/CpmChecks.h"
#include <iostream>
#include <fstream>
#include <iterator>
using namespace artery::cpm_a2;
static int assertions=0;
void check(bool condition,const char* label) { if(!condition) throw std::runtime_error(label); ++assertions; }
double control(Conversion& converted, bool fail=false) {
    F2MD_CPParameters params; params.MAX_PLAUSIBLE_SPEED=70;
    CpmChecks checks(&params); CpmCheckList list; list.resetAll();
    Scope scope(converted);
    if(fail) return evaluate(converted,[](double,double)->double { throw std::runtime_error("injected technical check error"); });
    return checks.CpmChecksum(converted.legacy,nullptr,list,nullptr);
}
int main(int argc,char** argv) {
    try {
        if(argc==3) {
            std::ifstream input(argv[1],std::ios::binary);
            vanetza::ByteBuffer bytes((std::istreambuf_iterator<char>(input)),{});
            auto message=decode(bytes); auto converted=convert(message);
            double value=control(converted);
            check(!converted.control.empty(),"actual CpmChecks R2 branch reached");
            Json result={{"result",value},{"checks",converted.control},{"objects",converted.objects},{"reference_time_ms",converted.reference_time_ms}};
            std::ofstream(argv[2]) << result.dump(2); return 0;
        }
        Json input={{"schema_version",2},{"frame","ENU"},{"velocity_frame","ground_ENU"},
            {"time_base","sumo_simulation_seconds"},{"frame_id",42},{"measurement_time_s",.4},
            {"reference",{{"latitude",50.3},{"longitude",3.5},{"heading_deg",90}}},
            {"objects",Json::array({{{"track_id",0},{"x",1.23},{"y",-2.34},{"vx",-3},{"vy",4},{"class","Car"}},
                {{"track_id",255},{"x",0},{"y",0},{"vx",0},{"vy",0},{"class","Pedestrian"}}})}};
        auto message=artery::perception::build(input,88,448538400500L,.5);
        auto converted=convert(decode(message.encode()));
        auto& list=converted.legacy->cpm.cpmParameters.perceivedObjectContainer->list;
        check(list.count==2,"object count"); check(list.array[0]->objectID==0 && list.array[1]->objectID==255,"IDs exact");
        check(list.array[0]->xDistance.value==123 && list.array[0]->yDistance.value==-234,"position units/sign");
        check(list.array[0]->xSpeed.value==-300 && list.array[0]->ySpeed.value==400,"velocity units/sign");
        check(list.array[0]->timeOfMeasurement==-100,"measurement delta sign");
        check(converted.reference_time_ms==448538400500L,"full timestamp");
        check(converted.legacy->cpm.generationDeltaTime==448538400500L%65536,"timestamp modulo");
        check(list.array[0]->classification->list.array[0]->Class.choice.vehicle.type==3,"R2 car5 -> oldcar3");
        check(list.array[1]->classification->list.array[0]->Class.choice.person.type==1,"pedestrian");
        check(!list.array[0]->xAcceleration && !list.array[0]->planarObjectDimension1,"absent values not fabricated");
        check(list.array[0]->xDistance.confidence==102,"unavailable confidence conversion");
        check(control(converted)==0 && converted.control["evaluated"].size()==2,"actual F2MD XY speed check");
        check(converted.control["complete"]==false && !converted.control["non_evaluable"].empty(),"partial status");
        auto unknown=input; unknown["objects"][0]["vx"]=nullptr; unknown["objects"][0]["vy"]=nullptr;
        unknown["objects"][1]["vx"]=nullptr; unknown["objects"][1]["vy"]=nullptr;
        auto absent=convert(artery::perception::build(unknown,88,448538400500L,.5)); control(absent);
        check(absent.legacy->cpm.cpmParameters.perceivedObjectContainer->list.array[0]->xSpeed.value==16383,"unknown velocity uses unavailable");
        check(absent.control["verdict"]=="non_evaluable" && absent.control["evaluated"].empty(),"no controls does not mean genuine");
        auto excessive=input; excessive["objects"][0]["vx"]=0; excessive["objects"][0]["vy"]=100;
        auto extreme=convert(artery::perception::build(excessive,88,448538400500L,.5));
        check(control(extreme)==1,"actual speed check sees lateral threshold violation");
        bool error=false;
        try { control(converted,true); } catch(const std::exception&) { error=true; }
        check(error,"technical error propagates, not genuine/anomaly");
        auto unsupported=input; unsupported["objects"][1]["track_id"]=256; error=false;
        try { convert(artery::perception::build(unsupported,88,448538400500L,.5)); } catch(const Unsupported&) {error=true;}
        check(error,"ID >255 rejected without remapping");
        auto old=input; old["measurement_time_s"]=-1.1; error=false;
        try { convert(artery::perception::build(old,88,448538400500L,.5)); } catch(const Unsupported&) {error=true;}
        check(error,"legacy measurement range");
        auto optional=input; optional["objects"][0]["length"]=4.5; optional["objects"][0]["ax"]=0; optional["objects"][0]["ay"]=0;
        auto withData=convert(artery::perception::build(optional,88,448538400500L,.5));
        auto* object=withData.legacy->cpm.cpmParameters.perceivedObjectContainer->list.array[0];
        check(object->planarObjectDimension1->value==45 && object->xAcceleration->longitudinalAccelerationValue==0,"present dimension and zero acceleration");
        auto bike=message; auto* o=bike->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list.array[0];
        auto& cl=o->classification->list.array[0]->objectClass;
        cl.present=Vanetza_ITS2_ObjectClass_PR_vruSubClass; cl.choice.vruSubClass.present=Vanetza_ITS2_VruProfileAndSubprofile_PR_bicyclistAndLightVruVehicle;
        cl.choice.vruSubClass.choice.bicyclistAndLightVruVehicle=1;
        auto mapped=convert(bike);
        check(mapped.legacy->cpm.cpmParameters.perceivedObjectContainer->list.array[0]->classification->list.array[0]->Class.choice.person.type==3,"bicyclist");
        cl.choice.vruSubClass.choice.bicyclistAndLightVruVehicle=2;
        mapped=convert(bike);
        check(mapped.legacy->cpm.cpmParameters.perceivedObjectContainer->list.array[0]->classification->list.array[0]->Class.choice.person.type==2,"wheelchair not cyclist");
        for(size_t size:{size_t(0),size_t(5),message.encode().size()-1}) {
            auto bytes=message.encode(); bytes.resize(size); error=false;
            try {decode(bytes);}catch(const std::exception&){error=true;}
            check(error,"truncation is technical error");
        }
        auto trailing=message.encode(); trailing.push_back(0); error=false;
        try { decode(trailing); }catch(const std::exception&){error=true;}
        check(error,"trailing input rejected");
        std::cout << Json({{"assertions",assertions},{"passed",true},{"actual_f2md_speed_check",true}}).dump(2) << std::endl;
    } catch(const std::exception& error) { std::cerr << error.what() << std::endl; return 1; }
}
