#include "artery-services/cpm/R2ToLegacy.h"
#include <fstream>
#include <iterator>
#include <iostream>
int main(int argc,char** argv) {
    if(argc!=3) return 2;
    using namespace artery::cpm_a2;
    Json record; std::string stage="decode";
    try {
        std::ifstream stream(argv[1],std::ios::binary);
        if(!stream) throw std::runtime_error("cannot open input");
        vanetza::ByteBuffer bytes((std::istreambuf_iterator<char>(stream)),{});
        auto message=decode(bytes); stage="convert";
        auto converted=convert(message);
        record={{"decoded",true},{"converted",true},{"legacy_valid",converted.legacy.validate()},
            {"reference_time_ms",converted.reference_time_ms},{"station_id",converted.legacy->header.stationID},
            {"legacy_delta_ms",converted.legacy->cpm.generationDeltaTime},{"objects",converted.objects},
            {"notes",converted.notes}};
        auto encoded=converted.legacy.encode();
        vanetza::asn1::Cpm decoded;
        if(!decoded.decode(encoded) || decoded!=converted.legacy) throw std::runtime_error("historical roundtrip failed");
        record["legacy_roundtrip"]=true;
        std::ofstream binary(std::string(argv[2])+".uper",std::ios::binary);
        for(auto byte:encoded) binary.put(static_cast<char>(byte));
        FILE* dump=std::fopen((std::string(argv[2])+".txt").c_str(),"w");
        converted.legacy.print(dump); std::fclose(dump);
    } catch(const Unsupported& error) {
        record={{"stage",stage},{"status","non_evaluable"},{"reason",error.what()}};
    } catch(const std::exception& error) {
        record={{"stage",stage},{"status","error"},{"reason",error.what()}};
    }
    std::ofstream(std::string(argv[2])+".json") << record.dump(2);
    std::cout << record.dump(2) << std::endl;
    return record.value("converted",false)?0:1;
}
