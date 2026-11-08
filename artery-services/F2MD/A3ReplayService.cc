#include "artery/application/ItsG5BaseService.h"
#include "R2ToLegacy.h"
#include <vanetza/btp/ports.hpp>
#include <cstdlib>
#include <fstream>
#include <iterator>
namespace artery {
class A3ReplayService : public ItsG5BaseService {
    cpm_a2::Json entries; std::size_t index=0;
public:
    void initialize() override {
        ItsG5BaseService::initialize();
        const char* path=std::getenv("EXFMD_A3_REPLAY");
        if(!path) throw std::runtime_error("A3 replay manifest missing");
        std::ifstream input(path); input>>entries;
    }
    void trigger() override {
        if(index>=entries.size() || omnetpp::simTime().dbl()+1e-10<entries[index].at("send_time_s").get<double>()) return;
        const auto& entry=entries[index];
        std::ifstream input(entry.at("path").get<std::string>(),std::ios::binary);
        vanetza::ByteBuffer bytes((std::istreambuf_iterator<char>(input)),{});
        auto message=cpm_a2::decode(bytes);
        using namespace vanetza;
        btp::DataRequestB req; req.destination_port=btp::ports::CPM; req.gn.its_aid=aid::CP;
        req.gn.transport_type=geonet::TransportType::SHB;
        req.gn.maximum_lifetime=geonet::Lifetime{geonet::Lifetime::Base::One_Second,1};
        req.gn.traffic_class.tc_id(static_cast<unsigned>(dcc::Profile::DP2)); req.gn.communication_profile=geonet::CommunicationProfile::ITS_G5;
        auto shared=std::make_shared<const asn1::r2::Cpm>(std::move(message));
        std::unique_ptr<geonet::DownPacket> payload(new geonet::DownPacket());
        payload->layer(OsiLayer::Application)=std::unique_ptr<convertible::byte_buffer>(new convertible::byte_buffer_impl<asn1::r2::Cpm>(shared));
        request(req,std::move(payload));
        std::cout<<"A3_REPLAY_TX "<<index++<<" "<<cpm_a2::hex(bytes)<<std::endl;
    }
};
Define_Module(A3ReplayService)
}
