#pragma once

// Shared by the running Artery service and the offline ASN.1 tests.
// JSON v2 is deliberately incompatible with unlabelled legacy relative velocity.
#include <vanetza/asn1/cpm.hpp>
#include <vanetza/asn1/its/r2/WrappedCpmContainer.h>
#include <vanetza/asn1/its/r2/PerceivedObject.h>
#include <vanetza/asn1/its/r2/OriginatingVehicleContainer.h>
#include <nlohmann/json.hpp>
#include <cmath>
#include <set>
#include <stdexcept>

namespace artery { namespace perception {
using Json = nlohmann::json;
inline double number(const Json& j, const char* key) {
    const auto& value = j.at(key);
    if (!value.is_number() || !std::isfinite(value.get<double>()))
        throw std::invalid_argument(std::string("finite number required: ") + key);
    return value.get<double>();
}
inline long scaled(double v, double scale, long low, long high) {
    if (!std::isfinite(v) || v * scale < low - 0.49 || v * scale > high + 0.49)
        throw std::invalid_argument("value outside supported physical range");
    return std::lround(v * scale);
}
inline bool available(const Json& j, const char* key) {
    return j.contains(key) && !j.at(key).is_null();
}
inline vanetza::asn1::r2::Cpm build(const Json& j, uint32_t station,
                                   long referenceTaiMs, double simulationTime) {
    if (j.at("schema_version") != 2 || j.at("frame") != "ENU" ||
        j.at("velocity_frame") != "ground_ENU" ||
        j.at("time_base") != "sumo_simulation_seconds")
        throw std::invalid_argument("unsupported perception contract/frame/time base");
    const double measurement = number(j, "measurement_time_s");
    const long delta = scaled(measurement - simulationTime, 1000, -2048, 0);
    if (!j.at("frame_id").is_number_integer() || j.at("frame_id").get<long>() < 0)
        throw std::invalid_argument("invalid measurement frame");
    const auto& objects = j.at("objects");
    if (!objects.is_array() || objects.empty() || objects.size() > 128)
        throw std::invalid_argument("object count must be 1..128 (no silent truncation)");
    vanetza::asn1::r2::Cpm message;
    auto& cpm = *message;
    cpm.header.protocolVersion = 2; cpm.header.messageId = 14;
    cpm.header.stationId = station;
    auto& mgmt = cpm.payload.managementContainer;
    asn_long2INTEGER(&mgmt.referenceTime, referenceTaiMs);
    const auto& ref = j.at("reference");
    mgmt.referencePosition.latitude = scaled(number(ref, "latitude"), 1e7, -900000000, 900000000);
    mgmt.referencePosition.longitude = scaled(number(ref, "longitude"), 1e7, -1800000000, 1800000000);
    mgmt.referencePosition.altitude.altitudeValue = 800001; // unavailable, not invented
    mgmt.referencePosition.altitude.altitudeConfidence = 15;
    mgmt.referencePosition.positionConfidenceEllipse.semiMajorConfidence = 4095;
    mgmt.referencePosition.positionConfidenceEllipse.semiMinorConfidence = 4095;
    mgmt.referencePosition.positionConfidenceEllipse.semiMajorOrientation = 3601;
    auto* vehicle = vanetza::asn1::allocate<Vanetza_ITS2_WrappedCpmContainer_t>();
    ASN_SEQUENCE_ADD(&cpm.payload.cpmContainers.list, vehicle);
    vehicle->containerId = 1;
    vehicle->containerData.present = Vanetza_ITS2_WrappedCpmContainer__containerData_PR_OriginatingVehicleContainer;
    auto& origin = vehicle->containerData.choice.OriginatingVehicleContainer;
    const double heading = number(ref, "heading_deg");
    if (heading < 0 || heading >= 360) throw std::invalid_argument("heading must be in [0,360)");
    origin.orientationAngle.value = std::lround(heading * 10) % 3600;
    origin.orientationAngle.confidence = 127;
    auto* wrapper = vanetza::asn1::allocate<Vanetza_ITS2_WrappedCpmContainer_t>();
    ASN_SEQUENCE_ADD(&cpm.payload.cpmContainers.list, wrapper);
    wrapper->containerId = 5;
    wrapper->containerData.present = Vanetza_ITS2_WrappedCpmContainer__containerData_PR_PerceivedObjectContainer;
    auto& poc = wrapper->containerData.choice.PerceivedObjectContainer;
    std::set<long> ids;
    for (const auto& obj : objects) {
        if (!obj.at("track_id").is_number_integer()) throw std::invalid_argument("track_id must be integer");
        long id = obj.at("track_id").get<long>();
        if (id < 0 || id > 65535 || !ids.insert(id).second) throw std::invalid_argument("invalid/duplicate track_id");
        auto* po = vanetza::asn1::allocate<Vanetza_ITS2_PerceivedObject_t>();
        ASN_SEQUENCE_ADD(&poc.perceivedObjects.list, po);
        po->objectId = vanetza::asn1::allocate<Vanetza_ITS2_Identifier2B_t>(); *po->objectId = id;
        po->measurementDeltaTime = delta;
        po->position.xCoordinate.value = scaled(number(obj, "x"), 100, -131071, 131070);
        po->position.yCoordinate.value = scaled(number(obj, "y"), 100, -131071, 131070);
        po->position.xCoordinate.confidence = 4096;
        po->position.yCoordinate.confidence = 4096;
        if (available(obj, "z")) {
            po->position.zCoordinate = vanetza::asn1::allocate<Vanetza_ITS2_CartesianCoordinateWithConfidence_t>();
            po->position.zCoordinate->value = scaled(number(obj, "z"), 100, -131071, 131070);
            po->position.zCoordinate->confidence = 4096;
        }
        if (available(obj, "vx") != available(obj, "vy")) throw std::invalid_argument("velocity needs both components");
        if (available(obj, "vx")) {
            po->velocity = vanetza::asn1::allocate<Vanetza_ITS2_Velocity3dWithConfidence_t>();
            po->velocity->present = Vanetza_ITS2_Velocity3dWithConfidence_PR_cartesianVelocity;
            auto& v = po->velocity->choice.cartesianVelocity;
            v.xVelocity.value = scaled(number(obj, "vx"), 100, -16382, 16381);
            v.yVelocity.value = scaled(number(obj, "vy"), 100, -16382, 16381);
            v.xVelocity.confidence = 127; v.yVelocity.confidence = 127;
        }
        if (available(obj, "ax") != available(obj, "ay")) throw std::invalid_argument("acceleration needs both components");
        if (available(obj, "ax")) {
            po->acceleration = vanetza::asn1::allocate<Vanetza_ITS2_Acceleration3dWithConfidence_t>();
            po->acceleration->present = Vanetza_ITS2_Acceleration3dWithConfidence_PR_cartesianAcceleration;
            auto& a = po->acceleration->choice.cartesianAcceleration;
            a.xAcceleration.value = scaled(number(obj, "ax"), 10, -159, 159);
            a.yAcceleration.value = scaled(number(obj, "ay"), 10, -159, 159);
            a.xAcceleration.confidence = 102; a.yAcceleration.confidence = 102;
        }
        auto dimension = [&](const char* key, Vanetza_ITS2_ObjectDimension_t*& target) {
            if (!available(obj, key)) return;
            long value = scaled(number(obj, key), 10, 1, 254);
            target = vanetza::asn1::allocate<Vanetza_ITS2_ObjectDimension_t>();
            target->value = value; target->confidence = 32;
        };
        dimension("length", po->objectDimensionX); dimension("width", po->objectDimensionY);
        dimension("height", po->objectDimensionZ);
        if (available(obj, "class")) {
            const std::string cls = obj.at("class").get<std::string>();
            if (cls == "Car" || cls == "Pedestrian" || cls == "Cyclist") {
                po->classification = vanetza::asn1::allocate<Vanetza_ITS2_ObjectClassDescription_t>();
                auto* c = vanetza::asn1::allocate<Vanetza_ITS2_ObjectClassWithConfidence_t>();
                ASN_SEQUENCE_ADD(&po->classification->list, c);
                c->confidence = 101;
                if (cls == "Car") {
                    c->objectClass.present = Vanetza_ITS2_ObjectClass_PR_vehicleSubClass;
                    c->objectClass.choice.vehicleSubClass = 5;
                } else {
                    c->objectClass.present = Vanetza_ITS2_ObjectClass_PR_vruSubClass;
                    auto& vru = c->objectClass.choice.vruSubClass;
                    vru.present = cls == "Pedestrian" ? Vanetza_ITS2_VruProfileAndSubprofile_PR_pedestrian : Vanetza_ITS2_VruProfileAndSubprofile_PR_bicyclistAndLightVruVehicle;
                    // The union's zero value means unspecified sub-profile, not unspecified VRU profile.
                }
            }
        }
    }
    poc.numberOfPerceivedObjects = objects.size();
    std::string error;
    if (!message.validate(error)) throw std::invalid_argument("invalid CPM: " + error);
    return message;
}
}} // namespace artery::perception
