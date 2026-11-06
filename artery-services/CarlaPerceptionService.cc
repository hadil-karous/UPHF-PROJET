#include "CarlaPerceptionService.h"
#include "artery/application/Asn1PacketVisitor.h"
#include "artery/application/Timer.h"
#include <vanetza/btp/ports.hpp>
#include <fstream>
#include <iostream>
#include <cstdlib>
#include <filesystem>
namespace artery {
using namespace omnetpp;
Define_Module(CarlaPerceptionService)
void CarlaPerceptionService::initialize() {
    ItsG5BaseService::initialize();
    mVehicleDataProvider = &getFacilities().get_const<VehicleDataProvider>();
    mTimer = &getFacilities().get_const<Timer>();
    mGenCpmMax = par("maxInterval");
    const std::string name = getParentModule()->getParentModule()->getName();
    std::string digits;
    for (char c : name) if (c >= '0' && c <= '9') digits += c;
    const char* directory = std::getenv("EXFMD_PERCEPTION_DIR");
    mJsonPath = std::string(directory ? directory : "/dev/shm") + "/perceived_" + (digits.empty() ? "0" : digits);
    mLastCpmTimestamp = simTime();
}
void CarlaPerceptionService::trigger() {
    if (simTime() - mLastCpmTimestamp >= mGenCpmMax) sendCpm(simTime());
}
void CarlaPerceptionService::sendCpm(const SimTime& now) {
    mLastCpmTimestamp = now;
    try {
        std::ifstream input(mJsonPath);
        if (!input) return;
        perception::Json data; input >> data;
        if (data.at("objects").empty()) return;
        const long referenceTime = countTaiMilliseconds(mTimer->getCurrentTime());
        auto message = perception::build(data, mVehicleDataProvider->getStationId(), referenceTime, now.dbl());
        // Optional evidence sidecar: frame is not added to the ETSI ASN.1 schema.
        // The encoded bytes are compared to the actual UDP/ROS packet capture.
        if (const char* directory = std::getenv("EXFMD_CPM_TRACE_DIR")) {
            std::filesystem::create_directories(directory);
            auto encoded = message.encode();
            static const char digits[] = "0123456789abcdef";
            std::string hex;
            for (auto byte : encoded) { hex += digits[byte >> 4]; hex += digits[byte & 15]; }
            perception::Json trace = {{"input",data},{"station_id",mVehicleDataProvider->getStationId()},
                {"reference_time_ms",referenceTime},{"simulation_time_s",now.dbl()},{"encoded_hex",hex}};
            const std::string name = std::to_string(mVehicleDataProvider->getStationId()) + "-" + std::to_string(referenceTime) + ".json";
            std::ofstream file(std::filesystem::path(directory) / name);
            if (!(file << trace.dump(2))) throw std::runtime_error("cannot archive CPM evidence");
        }
        using namespace vanetza;
        btp::DataRequestB req;
        req.destination_port = btp::ports::CPM;
        req.gn.its_aid = aid::CP;
        req.gn.transport_type = geonet::TransportType::SHB;
        req.gn.maximum_lifetime = geonet::Lifetime { geonet::Lifetime::Base::One_Second, 1 };
        req.gn.traffic_class.tc_id(static_cast<unsigned>(dcc::Profile::DP2));
        req.gn.communication_profile = geonet::CommunicationProfile::ITS_G5;
        auto shared = std::make_shared<const asn1::r2::Cpm>(std::move(message));
        using Buffer = convertible::byte_buffer_impl<asn1::r2::Cpm>;
        std::unique_ptr<geonet::DownPacket> payload(new geonet::DownPacket());
        payload->layer(OsiLayer::Application) = std::unique_ptr<convertible::byte_buffer>(new Buffer(shared));
        request(req, std::move(payload));
        std::cout << "CPM_A1_TX frame=" << data.at("frame_id") << " objects=" << data.at("objects").size() << std::endl;
    } catch (const std::exception& error) {
        std::cerr << "CPM_A1_REJECT " << error.what() << std::endl;
    }
}
void CarlaPerceptionService::indicate(const vanetza::btp::DataIndication&,
    std::unique_ptr<vanetza::UpPacket> packet) {
    // F2MD adaptation belongs after R2 decoding/validation, before onCPM.
    Asn1PacketVisitor<vanetza::asn1::r2::Cpm> visitor;
    const auto* cpm = boost::apply_visitor(visitor, *packet);
    if (cpm && cpm->validate()) std::cout << "CPM_A1_RX station=" << (*cpm)->header.stationId << std::endl;
}
const Timer* CarlaPerceptionService::getTimer() const { return mTimer; }
}
