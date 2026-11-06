#include "artery/application/ItsG5BaseService.h"
#include "R2ToLegacy.h"
#include <vanetza/btp/ports.hpp>
#include <fstream>
#include <iterator>
#include <cstdlib>
namespace artery {
class A2ReplayService : public ItsG5BaseService {
    cpm_a2::Json paths;
    size_t index=0;
    omnetpp::SimTime last;
public:
    void initialize() override {
        ItsG5BaseService::initialize();
        std::ifstream input(std::getenv("EXFMD_A2_REPLAY")); input>>paths;
        last=omnetpp::simTime();
    }
    void trigger() override {
        if(index>=paths.size() || omnetpp::simTime().dbl()<.21 || omnetpp::simTime()-last<omnetpp::SimTime(.1)) return;
        last=omnetpp::simTime();
        std::ifstream input(paths[index].get<std::string>(),std::ios::binary);
        vanetza::ByteBuffer bytes((std::istreambuf_iterator<char>(input)),{});
        auto message=cpm_a2::decode(bytes);
        using namespace vanetza;
        btp::DataRequestB req; req.destination_port=btp::ports::CPM; req.gn.its_aid=aid::CP;
        req.gn.transport_type=geonet::TransportType::SHB;
        req.gn.maximum_lifetime=geonet::Lifetime{geonet::Lifetime::Base::One_Second,1};
        req.gn.traffic_class.tc_id(static_cast<unsigned>(dcc::Profile::DP2));
        req.gn.communication_profile=geonet::CommunicationProfile::ITS_G5;
        auto shared=std::make_shared<const asn1::r2::Cpm>(std::move(message));
        std::unique_ptr<geonet::DownPacket> payload(new geonet::DownPacket());
        payload->layer(OsiLayer::Application)=std::unique_ptr<convertible::byte_buffer>(new convertible::byte_buffer_impl<asn1::r2::Cpm>(shared));
        request(req,std::move(payload));
        std::cout<<"A2_REPLAY_TX "<<index++<<" "<<cpm_a2::hex(bytes)<<std::endl;
    }
};
Define_Module(A2ReplayService)
}
