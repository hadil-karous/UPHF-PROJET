#include "CarlaPerceptionService.h"
#include "artery/application/ItsG5BaseService.h"
#include "artery/application/VehicleDataProvider.h"
#include "artery/application/Asn1PacketVisitor.h"
#include "artery/application/MultiChannelPolicy.h"
#include "artery/application/CpmObject.h"
#include "artery/utility/simtime_cast.h"
#include "Timer.h"
#include <vanetza/btp/ports.hpp>
#include <vanetza/asn1/cpm.hpp>
#include <vanetza/asn1/its/r2/CollectivePerceptionMessage.h>
#include <vanetza/asn1/its/r2/WrappedCpmContainer.h>
#include <vanetza/asn1/its/r2/PerceivedObject.h>
#include <vanetza/asn1/its/r2/PerceivedObjectContainer.h>
#include <vanetza/asn1/its/r2/CpmContainerId.h>
#include <vanetza/asn1/its/r2/MessageId.h>
#include <vanetza/asn1/its/r2/OriginatingVehicleContainer.h>
#include <vanetza/asn1/its/r2/Wgs84Angle.h>
#include <vanetza/asn1/its/r2/ObjectClass.h>
#include <vanetza/asn1/its/r2/VruProfileAndSubprofile.h>
#include <vanetza/asn1/its/r2/Acceleration3dWithConfidence.h>
#include <vanetza/asn1/its/r2/AccelerationCartesian.h>
#include <vanetza/asn1/its/r2/ObjectDimension.h>
#include <vanetza/asn1/its/r2/ObjectClassDescription.h>
#include <vanetza/asn1/its/r2/ObjectClassWithConfidence.h>
#include <vanetza/asn1/its/r2/CartesianCoordinateWithConfidence.h>
#include <vanetza/asn1/its/r2/TrafficParticipantType.h>
#include <omnetpp/cexception.h>
#include <boost/units/systems/si/prefixes.hpp>
#include <fstream>
#include <sstream>
#include <iostream>
#include <cmath>
#include <regex>
#include <fcntl.h>
#include <unistd.h>
#include <cstdint>

namespace artery
{

using namespace omnetpp;

static const auto centimeter_per_second =
    vanetza::units::si::meter_per_second * boost::units::si::centi;

Define_Module(CarlaPerceptionService)

void CarlaPerceptionService::initialize()
{
    ItsG5BaseService::initialize();
    mVehicleDataProvider = &getFacilities().get_const<VehicleDataProvider>();
    mTimer = &getFacilities().get_const<Timer>();
    mGenCpmMax = par("maxInterval");
    mFixedRate = par("fixedRate");
    // Chemin dynamique par noeud, comme CarlaCaService (node[i] -> perceived_i)
    std::string nodeName = getParentModule()->getParentModule()->getName();
    int nodeIdx = 0;
    std::string digits = "";
    for (char c : nodeName) { if (isdigit(c)) digits += c; }
    if (!digits.empty()) nodeIdx = std::stoi(digits);
    mJsonPath = "/dev/shm/perceived_" + std::to_string(nodeIdx);
    mLastCpmTimestamp = simTime();
    std::cout << "CarlaPerceptionService initialized, perceived=" << mJsonPath << std::endl;
}

void CarlaPerceptionService::trigger()
{
    std::cout << "CarlaPerceptionService::trigger called at " << simTime()
              << " elapsed=" << (simTime() - mLastCpmTimestamp)
              << " maxInterval=" << mGenCpmMax << std::endl;
    const SimTime T_elapsed = simTime() - mLastCpmTimestamp;
    if (T_elapsed >= mGenCpmMax) {
        sendCpm(simTime());
    }
}

void CarlaPerceptionService::indicate(
    const vanetza::btp::DataIndication& indication,
    std::unique_ptr<vanetza::UpPacket> packet)
{
    Asn1PacketVisitor<vanetza::asn1::Cpm> visitor;
    const vanetza::asn1::Cpm* cpm = boost::apply_visitor(visitor, *packet);
    if (!cpm || !cpm->validate()) return;

    const vanetza::asn1::Cpm& msg = *cpm;
    if (msg->cpm.cpmParameters.numberOfPerceivedObjects == 0) return;

    const PerceivedObjectContainer* poc =
        msg->cpm.cpmParameters.perceivedObjectContainer;
    if (!poc) return;

    std::string json = "{\"sender\":" +
        std::to_string(msg->header.stationID) +
        ",\"simtime\":" + std::to_string(simTime().dbl()) +
        ",\"objects\":[";

    for (int i = 0; i < poc->list.count; i++) {
        PerceivedObject_t* po = poc->list.array[i];
        if (i > 0) json += ",";
        json += "{\"id\":" + std::to_string(po->objectID) +
                ",\"x\":" + std::to_string(po->xDistance.value / 100.0) +
                ",\"y\":" + std::to_string(po->yDistance.value / 100.0) +
                ",\"vx\":" + std::to_string(po->xSpeed.value / 100.0) +
                "}";
    }
    json += "],\"count\":" + std::to_string(poc->list.count) + "}";

    std::string rxPath = mJsonPath.substr(0, mJsonPath.rfind('/')) +
        "/carla_received_cpm.json";
    std::ofstream f(rxPath);
    if (f.is_open()) {
        f << json;
        f.close();
        std::cout << "CarlaPerceptionService: received CPM from "
                  << msg->header.stationID
                  << " with " << poc->list.count
                  << " objects at " << SIMTIME_STR(simTime()) << std::endl;
    }
}

std::vector<CarlaObject> CarlaPerceptionService::readCarlaObjects()
{
    std::vector<CarlaObject> objects;
    std::ifstream file(mJsonPath);
    if (!file.is_open()) return objects;
    std::stringstream sbuf;
    sbuf << file.rdbuf();
    std::string content = sbuf.str();

    // Position de reference du detecteur (ref_lat / ref_lon a la racine du JSON)
    {
        std::smatch m;
        std::regex rlat("\"ref_lat\"\\s*:\\s*([-\\d.eE+]+)");
        std::regex rlon("\"ref_lon\"\\s*:\\s*([-\\d.eE+]+)");
        std::regex rhdg("\"ref_heading\"\\s*:\\s*([-\\d.eE+]+)");
        if (std::regex_search(content, m, rlat)) mRefLat = std::stod(m[1].str());
        if (std::regex_search(content, m, rlon)) mRefLon = std::stod(m[1].str());
        if (std::regex_search(content, m, rhdg)) mRefHeading = std::stod(m[1].str());
    }

    // Decoupe chaque objet { ... } puis extrait chaque champ par cle (ordre libre)
    std::regex obj_block(R"(\{[^}]*\})");
    auto num = [](const std::string& blk, const std::string& key, double def) -> double {
        std::smatch m;
        std::regex r("\"" + key + "\"\\s*:\\s*([-\\d.eE+]+)");
        if (std::regex_search(blk, m, r)) return std::stod(m[1].str());
        return def;
    };
    auto str = [](const std::string& blk, const std::string& key) -> std::string {
        std::smatch m;
        std::regex r("\"" + key + "\"\\s*:\\s*\"([^\"]*)\"");
        if (std::regex_search(blk, m, r)) return m[1].str();
        return std::string();
    };

    auto begin = std::sregex_iterator(content.begin(), content.end(), obj_block);
    auto end   = std::sregex_iterator();
    for (auto it = begin; it != end; ++it) {
        std::string blk = it->str();
        // un objet doit avoir au moins x et y
        if (blk.find("\"x\"") == std::string::npos ||
            blk.find("\"y\"") == std::string::npos) continue;
        CarlaObject obj;
        obj.x           = num(blk, "x", 0);
        obj.y           = num(blk, "y", 0);
        obj.z           = num(blk, "z", 0);
        obj.distance    = num(blk, "distance", 0);
        obj.point_count = (int)num(blk, "point_count", 0);
        obj.velocity    = num(blk, "velocity", 0);
        obj.ax          = num(blk, "ax", 0);
        obj.ay          = num(blk, "ay", 0);
        obj.length      = num(blk, "length", 0);
        obj.width       = num(blk, "width", 0);
        obj.obj_type    = (str(blk, "obj_type") == "vru") ? 1 : 0;
        objects.push_back(obj);
    }
    return objects;
}

void CarlaPerceptionService::sendCpm(const SimTime& T_now)
{
    auto objects = readCarlaObjects();
    mLastCpmTimestamp = T_now;
    // r2 : cpmContainers exige SIZE>=1, donc pas de CPM si aucun objet percu
    if (objects.empty()) {
        std::cout << "CarlaPerceptionService: no objects, skip CPM at "
                  << SIMTIME_STR(simTime()) << std::endl;
        return;
    }
    auto cpm = buildCpm(objects);

    using namespace vanetza;
    btp::DataRequestB request;
    request.destination_port = btp::ports::CPM;
    request.gn.its_aid = aid::CP;
    request.gn.transport_type = geonet::TransportType::SHB;
    request.gn.maximum_lifetime =
        geonet::Lifetime { geonet::Lifetime::Base::One_Second, 1 };
    request.gn.traffic_class.tc_id(
        static_cast<unsigned>(dcc::Profile::DP2));
    request.gn.communication_profile =
        geonet::CommunicationProfile::ITS_G5;

    auto cpm_ptr = std::make_shared<const asn1::r2::Cpm>(std::move(cpm));
    using CpmByteBuffer = convertible::byte_buffer_impl<asn1::r2::Cpm>;
    std::unique_ptr<geonet::DownPacket> payload { new geonet::DownPacket() };
    std::unique_ptr<convertible::byte_buffer> buffer {
        new CpmByteBuffer(cpm_ptr) };
    payload->layer(OsiLayer::Application) = std::move(buffer);
    this->request(request, std::move(payload));

    std::cout << "CarlaPerceptionService: sent CPM with "
              << objects.size() << " CARLA objects at "
              << SIMTIME_STR(simTime()) << std::endl;
}

vanetza::asn1::r2::Cpm CarlaPerceptionService::buildCpm(
    const std::vector<CarlaObject>& objects)
{
    vanetza::asn1::r2::Cpm message;
    Vanetza_ITS2_CollectivePerceptionMessage_t& cpm = *message;

    cpm.header.protocolVersion = 2;
    cpm.header.messageId       = Vanetza_ITS2_MessageId_cpm;
    cpm.header.stationId       = mVehicleDataProvider->getStationId() % 4294967295;

    Vanetza_ITS2_CPM_PDU_Descriptions_ManagementContainer_t& mgmt =
        cpm.payload.managementContainer;

    long referenceTime = countTaiMilliseconds(mTimer->getCurrentTime());
    asn_long2INTEGER(&mgmt.referenceTime, referenceTime);

    // Position de reference issue du detecteur CARLA (coherente avec les CAM, piste UPHF)
    long mlat = std::round(mRefLat * 1e7);
    long mlon = std::round(mRefLon * 1e7);
    mgmt.referencePosition.latitude =
        (mlat > -900000000 && mlat < 900000001) ? mlat : Latitude_unavailable;
    mgmt.referencePosition.longitude =
        (mlon > -1800000000 && mlon < 1800000001) ? mlon : Longitude_unavailable;
    mgmt.referencePosition.altitude.altitudeValue = AltitudeValue_unavailable;
    mgmt.referencePosition.altitude.altitudeConfidence = AltitudeConfidence_unavailable;
    mgmt.referencePosition.positionConfidenceEllipse.semiMinorConfidence =
        SemiAxisLength_unavailable;
    mgmt.referencePosition.positionConfidenceEllipse.semiMajorConfidence =
        SemiAxisLength_unavailable;
    mgmt.referencePosition.positionConfidenceEllipse.semiMajorOrientation =
        HeadingValue_unavailable;

    // --- OriginatingVehicleContainer (heading du detecteur) ---
    {
        Vanetza_ITS2_WrappedCpmContainer_t* ovcWrap =
            vanetza::asn1::allocate<Vanetza_ITS2_WrappedCpmContainer_t>();
        ovcWrap->containerId = Vanetza_ITS2_CpmContainerId_originatingVehicleContainer;
        ovcWrap->containerData.present =
            Vanetza_ITS2_WrappedCpmContainer__containerData_PR_OriginatingVehicleContainer;
        Vanetza_ITS2_OriginatingVehicleContainer_t& ovc =
            ovcWrap->containerData.choice.OriginatingVehicleContainer;
        long hdg = (long)std::round(mRefHeading * 10.0);  // deg -> 0.1 deg
        if (hdg < 0) hdg = 0; if (hdg > 3600) hdg = 3600;
        ovc.orientationAngle.value      = hdg;
        ovc.orientationAngle.confidence = Vanetza_ITS2_AngleConfidence_unavailable;
        ASN_SEQUENCE_ADD(&cpm.payload.cpmContainers.list, ovcWrap);
    }


    if (!objects.empty()) {
        Vanetza_ITS2_WrappedCpmContainer_t* wrapped =
            vanetza::asn1::allocate<Vanetza_ITS2_WrappedCpmContainer_t>();
        wrapped->containerId = Vanetza_ITS2_CpmContainerId_perceivedObjectContainer;
        wrapped->containerData.present =
            Vanetza_ITS2_WrappedCpmContainer__containerData_PR_PerceivedObjectContainer;

        Vanetza_ITS2_PerceivedObjectContainer_t& poc =
            wrapped->containerData.choice.PerceivedObjectContainer;

        int objID = 1;
        int maxObj = 10; int objCount = 0;
        for (const auto& obj : objects) {
            if (objCount++ >= maxObj) break;

            Vanetza_ITS2_PerceivedObject_t* po =
                vanetza::asn1::allocate<Vanetza_ITS2_PerceivedObject_t>();

            po->objectId = vanetza::asn1::allocate<Vanetza_ITS2_Identifier2B_t>();
            *po->objectId = objID++;
            po->measurementDeltaTime = 0;

            // --- position (x, y) ---
            double dx = std::max(-32768.0, std::min(32767.0, obj.x * 100.0));
            double dy = std::max(-32768.0, std::min(32767.0, obj.y * 100.0));
            po->position.xCoordinate.value      = (long)dx;
            po->position.xCoordinate.confidence = Vanetza_ITS2_CoordinateConfidence_unavailable;
            po->position.yCoordinate.value      = (long)dy;
            po->position.yCoordinate.confidence = Vanetza_ITS2_CoordinateConfidence_unavailable;

            // --- zCoordinate (OPTIONAL) ---
            double dz = std::max(-32768.0, std::min(32767.0, obj.z * 100.0));
            po->position.zCoordinate =
                vanetza::asn1::allocate<Vanetza_ITS2_CartesianCoordinateWithConfidence_t>();
            po->position.zCoordinate->value      = (long)dz;
            po->position.zCoordinate->confidence = Vanetza_ITS2_CoordinateConfidence_unavailable;

            // --- velocity (cartesienne) ---
            po->velocity = vanetza::asn1::allocate<Vanetza_ITS2_Velocity3dWithConfidence_t>();
            po->velocity->present =
                Vanetza_ITS2_Velocity3dWithConfidence_PR_cartesianVelocity;
            long vel_cms = (long)(std::abs(obj.velocity) * 100.0);
            vel_cms = std::max(-16383L, std::min(16383L, vel_cms));
            po->velocity->choice.cartesianVelocity.xVelocity.value      = vel_cms;
            po->velocity->choice.cartesianVelocity.xVelocity.confidence = Vanetza_ITS2_SpeedConfidence_unavailable;
            po->velocity->choice.cartesianVelocity.yVelocity.value      = 0;
            po->velocity->choice.cartesianVelocity.yVelocity.confidence = Vanetza_ITS2_SpeedConfidence_unavailable;

            // --- acceleration (cartesienne) ---
            po->acceleration = vanetza::asn1::allocate<Vanetza_ITS2_Acceleration3dWithConfidence_t>();
            po->acceleration->present =
                Vanetza_ITS2_Acceleration3dWithConfidence_PR_cartesianAcceleration;
            long ax_dm = std::max(-160L, std::min(160L, (long)std::round(obj.ax * 10.0)));
            long ay_dm = std::max(-160L, std::min(160L, (long)std::round(obj.ay * 10.0)));
            po->acceleration->choice.cartesianAcceleration.xAcceleration.value      = ax_dm;
            po->acceleration->choice.cartesianAcceleration.xAcceleration.confidence = Vanetza_ITS2_AccelerationConfidence_unavailable;
            po->acceleration->choice.cartesianAcceleration.yAcceleration.value      = ay_dm;
            po->acceleration->choice.cartesianAcceleration.yAcceleration.confidence = Vanetza_ITS2_AccelerationConfidence_unavailable;

            // --- dimensions (X = longueur, Y = largeur) en 0.1 m ---
            if (obj.length > 0) {
                po->objectDimensionX = vanetza::asn1::allocate<Vanetza_ITS2_ObjectDimension_t>();
                po->objectDimensionX->value      = std::max(1L, std::min(255L, (long)std::round(obj.length * 10.0)));
                po->objectDimensionX->confidence = Vanetza_ITS2_ObjectDimensionConfidence_unavailable;
            }
            if (obj.width > 0) {
                po->objectDimensionY = vanetza::asn1::allocate<Vanetza_ITS2_ObjectDimension_t>();
                po->objectDimensionY->value      = std::max(1L, std::min(255L, (long)std::round(obj.width * 10.0)));
                po->objectDimensionY->confidence = Vanetza_ITS2_ObjectDimensionConfidence_unavailable;
            }

            // --- classification (vehicle / VRU) ---
            po->classification =
                vanetza::asn1::allocate<Vanetza_ITS2_ObjectClassDescription_t>();
            Vanetza_ITS2_ObjectClassWithConfidence_t* ocwc =
                vanetza::asn1::allocate<Vanetza_ITS2_ObjectClassWithConfidence_t>();
            if (obj.obj_type == 1) {
                ocwc->objectClass.present = Vanetza_ITS2_ObjectClass_PR_vruSubClass;
                // vruSubClass : profil pieton par defaut (CHOICE pedestrian)
                ocwc->objectClass.choice.vruSubClass.present =
                    Vanetza_ITS2_VruProfileAndSubprofile_PR_pedestrian;
                ocwc->objectClass.choice.vruSubClass.choice.pedestrian = 0; // unavailable
            } else {
                ocwc->objectClass.present = Vanetza_ITS2_ObjectClass_PR_vehicleSubClass;
                ocwc->objectClass.choice.vehicleSubClass =
                    Vanetza_ITS2_TrafficParticipantType_passengerCar;
            }
            ocwc->confidence = Vanetza_ITS2_ConfidenceLevel_unavailable;
            ASN_SEQUENCE_ADD(&po->classification->list, ocwc);

            ASN_SEQUENCE_ADD(&poc.perceivedObjects.list, po);
        }
        poc.numberOfPerceivedObjects = poc.perceivedObjects.list.count;

        ASN_SEQUENCE_ADD(&cpm.payload.cpmContainers.list, wrapped);
    }

    return message;
}

const Timer* CarlaPerceptionService::getTimer() const
{
    return mTimer;
}

} // namespace artery
