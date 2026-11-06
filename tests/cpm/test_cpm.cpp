#include "artery-services/cpm/PerceptionCpm.h"
#include <fstream>
#include <iostream>
#include <functional>
using artery::perception::Json;
static int checks = 0;
void require(bool ok, const char* name) {
    if (!ok) throw std::runtime_error(name);
    ++checks;
}
void rejects(const Json& j, const char* name) {
    bool rejected = false;
    try { artery::perception::build(j, 88, 448538400500L, 0.5); }
    catch (const std::exception&) { rejected = true; }
    require(rejected, name);
}
int main(int argc, char** argv) {
    try {
        Json input = {{"schema_version",2}, {"frame","ENU"}, {"velocity_frame","ground_ENU"},
            {"time_base","sumo_simulation_seconds"}, {"measurement_time_s",0.4}, {"frame_id",42},
            {"reference",{{"latitude",50.3184295},{"longitude",3.5104363},{"heading_deg",90.0}}},
            {"objects",Json::array({{{"track_id",71},{"x",1.234},{"y",-2.346},{"z",nullptr},
                {"vx",-3.0},{"vy",4.0},{"velocity",5.0},{"class","Pedestrian"}},
                {{"track_id",9},{"x",0},{"y",0},{"vx",0},{"vy",0},{"class","Cyclist"}}})}};
        auto before = input;
        auto msg = artery::perception::build(input,88,448538400500L,0.5);
        auto bytes = msg.encode();
        vanetza::asn1::r2::Cpm decoded;
        require(decoded.decode(bytes),"R2 decode"); require(decoded.validate(),"R2 constraints");
        require(decoded == msg,"encode/decode equality");
        for (size_t size : {size_t(0), size_t(10), bytes.size()-1}) {
            vanetza::ByteBuffer truncated(bytes.begin(),bytes.begin()+size);
            vanetza::asn1::r2::Cpm incomplete;
            require(!incomplete.decode(truncated),"truncated payload rejected");
        }
        auto& list = decoded->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list;
        require(*list.array[0]->objectId == 71 && *list.array[1]->objectId == 9,"stable track IDs");
        require(list.array[0]->position.xCoordinate.value == 123 && list.array[0]->position.yCoordinate.value == -235,"signed cm rounding");
        require(list.array[0]->measurementDeltaTime == -100,"measurement age");
        auto& velocity = list.array[0]->velocity->choice.cartesianVelocity;
        require(velocity.xVelocity.value == -300 && velocity.yVelocity.value == 400,"signed lateral cm/s");
        require(!list.array[0]->position.zCoordinate && !list.array[0]->acceleration && !list.array[0]->objectDimensionX && !list.array[0]->sensorIdList,"unknown fields absent");
        require(list.array[1]->velocity && list.array[1]->velocity->choice.cartesianVelocity.xVelocity.value == 0,"actual zero preserved");
        auto& ped = list.array[0]->classification->list.array[0]->objectClass;
        auto& bike = list.array[1]->classification->list.array[0]->objectClass;
        require(ped.choice.vruSubClass.present == Vanetza_ITS2_VruProfileAndSubprofile_PR_pedestrian,"pedestrian mapped");
        require(bike.choice.vruSubClass.present == Vanetza_ITS2_VruProfileAndSubprofile_PR_bicyclistAndLightVruVehicle,"cyclist mapped");
        std::swap(input["objects"][0],input["objects"][1]);
        auto reordered = artery::perception::build(input,88,448538400500L,0.5);
        require(*reordered->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list.array[0]->objectId == 9,"order does not reassign ID");
        input=before; input["objects"][0].erase("vx"); input["objects"][0].erase("vy");
        auto unknown=artery::perception::build(input,88,448538400500L,0.5);
        require(!unknown->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list.array[0]->velocity,"unknown velocity absent");
        input=before; input["objects"][0]["vx"]=nullptr; input["objects"][0]["vy"]=nullptr;
        auto nullVelocity=artery::perception::build(input,88,448538400500L,0.5);
        require(!nullVelocity->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list.array[0]->velocity,"null velocity absent");
        input=before; input["objects"][0]["track_id"]=0; input["objects"][1]["track_id"]=65535;
        auto ids=artery::perception::build(input,88,448538400500L,0.5);
        auto& idList=ids->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list;
        require(*idList.array[0]->objectId==0 && *idList.array[1]->objectId==65535,"ID range including zero");
        input=before; input["reference"]["heading_deg"]=359.99;
        auto north=artery::perception::build(input,88,448538400500L,0.5);
        require(north->payload.cpmContainers.list.array[0]->containerData.choice.OriginatingVehicleContainer.orientationAngle.value==0,"north wrap after quantization");
        input=before; input["objects"][0]["ax"]=0; input["objects"][0]["ay"]=0; input["objects"][0]["length"]=4.5;
        auto optional=artery::perception::build(input,88,448538400500L,0.5);
        auto* opt=optional->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list.array[0];
        require(opt->acceleration && opt->acceleration->choice.cartesianAcceleration.xAcceleration.value==0 && opt->objectDimensionX->value==45,"supplied optional zero and dm");
        input=before; input["objects"][0]["class"]="unknown";
        auto unclassified=artery::perception::build(input,88,448538400500L,0.5);
        require(!unclassified->payload.cpmContainers.list.array[1]->containerData.choice.PerceivedObjectContainer.perceivedObjects.list.array[0]->classification,"unknown class not car");
        input=before; input["objects"][0].erase("track_id"); rejects(input,"missing ID");
        input=before; input["objects"][0]["track_id"]=9; rejects(input,"duplicate ID");
        input=before; input["objects"][0]["track_id"]=65536; rejects(input,"ID overflow");
        input=before; input["objects"][0]["track_id"]=1.5; rejects(input,"fractional ID");
        input=before; input["objects"][0]["vx"]=nullptr; rejects(input,"incomplete velocity");
        input=before; input["objects"][0]["vx"]=163.83; rejects(input,"sentinel is not speed");
        input=before; input["objects"][0]["x"]=2000; rejects(input,"coordinate range");
        input=before; input["objects"][0]["length"]=0; rejects(input,"zero is not valid dimension");
        input=before; input["measurement_time_s"]=1.0; rejects(input,"future timestamp");
        input=before; input["measurement_time_s"]=-3; rejects(input,"stale timestamp");
        input=before; input["frame"]="lidar"; rejects(input,"moving frame");
        input=before; input["time_base"]="carla_simulation_seconds"; rejects(input,"unaligned clock");
        input=before; input["schema_version"]=1; rejects(input,"legacy schema");
        if (argc>1) {
            std::string out=argv[1];
            std::ofstream(out+"/fixture-v2.json") << before.dump(2);
            std::ofstream f(out+"/corrected.uper",std::ios::binary);
            f.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
            Json result={{"assertions",checks},{"passed",true},{"encoded_bytes",bytes.size()}};
            std::ofstream(out+"/cpp-tests.json") << result.dump(2);
        }
        std::cout << "PASS " << checks << " C++ assertions; actual Vanetza R2 roundtrip" << std::endl;
    } catch(const std::exception& e) { std::cerr << "FAIL " << e.what() << std::endl; return 1; }
}
