#include "artery-services/cpm/R2ToLegacy.h"
#include <fstream>
#include <iostream>
#include <iterator>
using Json=nlohmann::json;
Json objects(const vanetza::asn1::r2::Cpm& msg) {
    Json result=Json::array();
    for(int n=0;n<msg->payload.cpmContainers.list.count;++n) {
        const auto& c=msg->payload.cpmContainers.list.array[n]->containerData;
        if(c.present!=Vanetza_ITS2_WrappedCpmContainer__containerData_PR_PerceivedObjectContainer) continue;
        for(int i=0;i<c.choice.PerceivedObjectContainer.perceivedObjects.list.count;++i) {
            const auto& o=*c.choice.PerceivedObjectContainer.perceivedObjects.list.array[i];
            Json row={{"id",*o.objectId},{"x_cm",o.position.xCoordinate.value},{"y_cm",o.position.yCoordinate.value},
                {"z_cm",o.position.zCoordinate->value},{"measurement_delta_ms",o.measurementDeltaTime}};
            if(o.acceleration || o.objectDimensionX || o.objectDimensionY || o.sensorIdList) throw std::runtime_error("unavailable data fabricated");
            if(o.velocity) {
                const auto& v=o.velocity->choice.cartesianVelocity;
                row["vx_cm_s"]=v.xVelocity.value; row["vy_cm_s"]=v.yVelocity.value;
                if(v.xVelocity.confidence!=127 || v.yVelocity.confidence!=127) throw std::runtime_error("uncalibrated confidence converted");
            }
            result.push_back(row);
        }
    }
    return result;
}
int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("index and output directory required");
        Json index; std::ifstream(argv[1])>>index; Json compared=Json::array(); int different=0;
        for(const auto& entry:index) {
            Json pair={{"capture_index",entry["capture_index"]},{"frame_id",entry["frame_id"]},{"source_sha256",entry["source_sha256"]}};
            vanetza::ByteBuffer baseline;
            for(const std::string variant:{"baseline","cwa_q2"}) {
                Json data; std::ifstream(entry[variant].get<std::string>())>>data;
                auto msg=artery::perception::build(data,entry["station"],entry["reference_time_ms"],entry["simulation_time_s"]);
                const auto bytes=msg.encode(); auto decoded=artery::cpm_a2::decode(bytes);
                pair[variant]=objects(decoded);
                if(variant=="baseline") {
                    std::ifstream original(entry["expected"].get<std::string>(),std::ios::binary);
                    if(!original) throw std::runtime_error("cannot open archived source");
                    vanetza::ByteBuffer expected((std::istreambuf_iterator<char>(original)),{});
                    if(bytes!=expected) throw std::runtime_error("baseline does not reproduce archived UPER");
                    baseline=bytes;
                } else {pair["packet_changed"]=bytes!=baseline; different+=bytes!=baseline;}
                std::ofstream output(std::string(argv[2])+"/"+variant+"-"+std::to_string(entry["capture_index"].get<int>())+".uper",std::ios::binary);
                for(auto b:bytes) output.put(static_cast<char>(b));
            }
            for(size_t i=0;i<pair["baseline"].size();++i) {
                if(pair["baseline"][i]["id"]!=pair["cwa_q2"][i]["id"] || pair["baseline"][i]["measurement_delta_ms"]!=pair["cwa_q2"][i]["measurement_delta_ms"])
                    throw std::runtime_error("identifier or timestamp changed");
            }
            compared.push_back(pair);
        }
        Json result={{"passed",true},{"baseline_exact_packets",compared.size()},{"candidate_valid_packets",compared.size()},
            {"candidate_changed_packets",different},{"comparisons",compared},{"f2md_executed",false}};
        std::ofstream(std::string(argv[2])+"/comparison.json")<<result.dump(2);
        std::cout<<"Exact baseline and valid candidate: "<<compared.size()<<", changed candidate packets: "<<different<<std::endl;
    }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}
}
