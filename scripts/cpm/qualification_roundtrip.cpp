#include "artery-services/cpm/PerceptionCpm.h"
#include "artery-services/cpm/R2ToLegacy.h"
#include <fstream>
#include <iostream>
#include <iterator>
int main(int argc,char** argv) {
    try {
        if(argc!=3) throw std::runtime_error("fixture-index output-json required");
        nlohmann::json index; std::ifstream(argv[1])>>index;
        nlohmann::json comparisons=nlohmann::json::array();
        for(const auto& entry:index) {
            nlohmann::json data; std::ifstream(entry.at("input").get<std::string>())>>data;
            for(const auto& object:data.at("objects")) {
                const auto& quality=object.at("estimation_quality");
                if(quality.at("physically_calibrated")!=false) throw std::runtime_error("fabricated calibrated quality");
            }
            auto cpm=artery::perception::build(data,entry.at("station"),entry.at("reference_time_ms"),entry.at("simulation_time_s"));
            auto bytes=cpm.encode(); auto decoded=artery::cpm_a2::decode(bytes);
            std::ifstream input(entry.at("expected").get<std::string>(),std::ios::binary);
            if(!input) throw std::runtime_error("cannot open original UPER: "+entry.at("expected").get<std::string>());
            vanetza::ByteBuffer expected((std::istreambuf_iterator<char>(input)),{});
            if(bytes!=expected || decoded.encode()!=expected) {
                std::ofstream(std::string(argv[2])+".failure.json")<<nlohmann::json({{"entry",entry},{"matched_before_failure",comparisons.size()},
                    {"actual_hex",artery::cpm_a2::hex(bytes)},{"expected_hex",artery::cpm_a2::hex(expected)},{"input",data}}).dump(2);
                throw std::runtime_error("UPER mismatch at capture "+std::to_string(entry.at("capture_index").get<int>()));
            }
            comparisons.push_back({{"frame_id",entry.at("frame_id")},{"capture_index",entry.at("capture_index")},
                {"source_sha256",entry.at("sha256")},{"bytes",bytes.size()},{"exact_uper_match",true},{"decode_valid",true}});
        }
        std::ofstream(argv[2])<<nlohmann::json({{"passed",true},{"packets",comparisons.size()},{"comparisons",comparisons}}).dump(2);
        std::cout<<"UPER roundtrips and metadata invariance: "<<comparisons.size()<<std::endl;
    }catch(const std::exception& e) {std::cerr<<e.what()<<std::endl; return 1;}
}
