#pragma once
// Explicit field conversion between the image's two generated ASN.1 schemas.
// Full R2 bytes/time and losses remain in the accompanying result; never cast
// one generated structure to the other or renumber an unrepresentable ID.
#include "PerceptionCpm.h"
#include <vanetza/asn1/support/per_decoder.h>
#include <map>
#include <functional>
#include <cstdint>

namespace artery { namespace cpm_a3 { struct Context; }}

namespace artery { namespace cpm_a2 {
using Json=nlohmann::json;
struct Unsupported : std::runtime_error { using std::runtime_error::runtime_error; };
struct Conversion {
    vanetza::asn1::Cpm legacy;
    std::int64_t reference_time_ms=0;
    cpm_a3::Context* temporal_context=nullptr;
    Json notes=Json::array(), objects=Json::array();
    std::map<long,bool> velocity_available;
    Json control=Json::object();
};
inline thread_local Conversion* active_conversion=nullptr;
struct Scope {
    Conversion* prior;
    explicit Scope(Conversion& c):prior(active_conversion) { active_conversion=&c; }
    ~Scope() { active_conversion=prior; }
    Scope(const Scope&)=delete;
};
inline std::string hex(const vanetza::ByteBuffer& bytes) {
    static const char digits[]="0123456789abcdef";
    std::string out;
    for(auto b:bytes) { out+=digits[b>>4]; out+=digits[b&15]; }
    return out;
}
inline vanetza::asn1::r2::Cpm decode(const vanetza::ByteBuffer& bytes) {
    vanetza::asn1::r2::Cpm message;
    if(!message.decode(bytes)) throw std::runtime_error("R2 UPER decode failed");
    std::string error;
    if(!message.validate(error)) throw std::runtime_error("R2 constraints: "+error);
    if(message.encode()!=bytes) throw std::runtime_error("non-canonical or trailing R2 data");
    return message;
}
inline long distance_confidence(long value) {
    if(value==4096) return 102;
    if(value>=101) return 101; // known accuracy outside the old representable range
    return value;
}
inline long dimension_confidence(long value) {
    if(value==32) return 102;
    if(value==31 || value*10>100) return 101;
    return value*10; // R2 0.1m -> historical 0.01m
}
inline Conversion convert(const vanetza::asn1::r2::Cpm& input,bool envelope_only=false) {
    std::string error;
    if(!input.validate(error)) throw std::runtime_error("invalid R2: "+error);
    Conversion result;
    auto note=[&](const std::string& field,const std::string& reason) {
        result.notes.push_back({{"field",field},{"reason",reason}});
    };
    auto& output=*result.legacy;
    output.header.protocolVersion=input->header.protocolVersion;
    output.header.messageID=input->header.messageId;
    output.header.stationID=input->header.stationId;
    long decoded_reference=0;
    static_assert(sizeof(long)>=8,"ASN.1 image runtime requires a 64-bit long");
    if(asn_INTEGER2long(&input->payload.managementContainer.referenceTime,&decoded_reference))
        throw Unsupported("referenceTime outside host integer range");
    result.reference_time_ms=decoded_reference;
    output.cpm.generationDeltaTime=result.reference_time_ms%65536;
    note("referenceTime","full milliseconds kept in sidecar; legacy field is modulo 65536");
    auto& management=output.cpm.cpmParameters.managementContainer;
    const auto& ref=input->payload.managementContainer.referencePosition;
    management.stationType=StationType_unknown;
    management.referencePosition.latitude=ref.latitude;
    management.referencePosition.longitude=ref.longitude;
    management.referencePosition.altitude.altitudeValue=ref.altitude.altitudeValue;
    management.referencePosition.altitude.altitudeConfidence=ref.altitude.altitudeConfidence;
    auto& ellipse=management.referencePosition.positionConfidenceEllipse;
    ellipse.semiMajorConfidence=ref.positionConfidenceEllipse.semiMajorConfidence;
    ellipse.semiMinorConfidence=ref.positionConfidenceEllipse.semiMinorConfidence;
    ellipse.semiMajorOrientation=ref.positionConfidenceEllipse.semiMajorOrientation;
    note("stationType","R2 originating vehicle kind does not identify a vehicle subclass; unknown");
    auto& params=output.cpm.cpmParameters;
    bool hadObjects=false,hadVehicle=false;
    for(int n=0;n<input->payload.cpmContainers.list.count;++n) {
        const auto& wrap=*input->payload.cpmContainers.list.array[n];
        if(wrap.containerData.present==Vanetza_ITS2_WrappedCpmContainer__containerData_PR_OriginatingVehicleContainer) {
            if(hadVehicle) throw Unsupported("multiple originating vehicle containers");
            hadVehicle=true;
            params.stationDataContainer=vanetza::asn1::allocate<StationDataContainer_t>();
            params.stationDataContainer->present=StationDataContainer_PR_originatingVehicleContainer;
            auto& vehicle=params.stationDataContainer->choice.originatingVehicleContainer;
            vehicle.heading.headingValue=HeadingValue_unavailable;
            vehicle.heading.headingConfidence=HeadingConfidence_unavailable;
            vehicle.speed.speedValue=SpeedValue_unavailable;
            vehicle.speed.speedConfidence=SpeedConfidence_unavailable;
            vehicle.vehicleOrientationAngle=vanetza::asn1::allocate<WGS84Angle_t>();
            const auto& origin=wrap.containerData.choice.OriginatingVehicleContainer;
            vehicle.vehicleOrientationAngle->value=origin.orientationAngle.value;
            vehicle.vehicleOrientationAngle->confidence=origin.orientationAngle.confidence;
            if(origin.pitchAngle || origin.rollAngle || origin.trailerDataSet)
                note("originatingVehicle","pitch/roll/trailers retained in source R2 only");
            continue;
        }
        if(wrap.containerData.present!=Vanetza_ITS2_WrappedCpmContainer__containerData_PR_PerceivedObjectContainer) {
            note("container_"+std::to_string(wrap.containerId),"not mapped; original R2 retained; coverage controls unavailable");
            continue;
        }
        if(hadObjects) throw Unsupported("multiple object containers not supported");
        hadObjects=true;
        const auto& poc=wrap.containerData.choice.PerceivedObjectContainer;
        if(envelope_only) {
            note("perceivedObjects","A3 native R2 model; no historical IDs or deltas fabricated; legacy envelope contains no objects");
            continue;
        }
        if(poc.numberOfPerceivedObjects>255) throw Unsupported("total object count exceeds historical range");
        params.numberOfPerceivedObjects=poc.numberOfPerceivedObjects;
        params.perceivedObjectContainer=vanetza::asn1::allocate<PerceivedObjectContainer_t>();
        for(int i=0;i<poc.perceivedObjects.list.count;++i) {
            const auto& src=*poc.perceivedObjects.list.array[i];
            if(!src.objectId) throw Unsupported("object ID absent; no ID will be invented");
            long id=*src.objectId;
            if(id>255) throw Unsupported("R2 object ID "+std::to_string(id)+" exceeds historical 0..255; no renumbering");
            if(result.velocity_available.count(id)) throw Unsupported("duplicate object ID");
            if(src.measurementDeltaTime < -1500 || src.measurementDeltaTime>1500)
                throw Unsupported("measurement delta outside historical -1500..1500ms");
            auto* dst=vanetza::asn1::allocate<PerceivedObject_t>();
            ASN_SEQUENCE_ADD(params.perceivedObjectContainer,dst);
            dst->objectID=id; dst->timeOfMeasurement=src.measurementDeltaTime;
            auto position=[&](const Vanetza_ITS2_CartesianCoordinateWithConfidence_t& a,ObjectDistanceWithConfidence_t& b) {
                if(a.value==-131072 || a.value==131071) throw Unsupported("R2 coordinate out-of-range sentinel has no old equivalent");
                b.value=a.value; b.confidence=distance_confidence(a.confidence);
                if(a.confidence>100 && a.confidence<4095) note("positionConfidence","accuracy outside historical range; original kept");
            };
            position(src.position.xCoordinate,dst->xDistance); position(src.position.yCoordinate,dst->yDistance);
            if(src.position.zCoordinate) { dst->zDistance=vanetza::asn1::allocate<ObjectDistanceWithConfidence_t>(); position(*src.position.zCoordinate,*dst->zDistance); }
            dst->xSpeed={SpeedValueExtended_unavailable,SpeedConfidence_unavailable,{}};
            dst->ySpeed={SpeedValueExtended_unavailable,SpeedConfidence_unavailable,{}};
            bool velocity=false;
            if(src.velocity && src.velocity->present==Vanetza_ITS2_Velocity3dWithConfidence_PR_cartesianVelocity) {
                const auto& v=src.velocity->choice.cartesianVelocity;
                auto speed=[&](const auto& a,SpeedExtended_t& b) {
                    if(a.value==-16383 || a.value>=16382) { note("velocity","unavailable/out-of-range component preserved as unavailable"); return false; }
                    b.value=a.value; b.confidence=a.confidence; return true;
                };
                bool x=speed(v.xVelocity,dst->xSpeed),y=speed(v.yVelocity,dst->ySpeed); velocity=x&&y;
                if(v.zVelocity) { dst->zSpeed=vanetza::asn1::allocate<SpeedExtended_t>(); dst->zSpeed->value=SpeedValueExtended_unavailable; dst->zSpeed->confidence=SpeedConfidence_unavailable; speed(*v.zVelocity,*dst->zSpeed); }
            } else note("velocity","absent or non-cartesian; mandatory old components set unavailable, not zero");
            result.velocity_available[id]=velocity;
            if(src.acceleration && src.acceleration->present==Vanetza_ITS2_Acceleration3dWithConfidence_PR_cartesianAcceleration) {
                const auto& a=src.acceleration->choice.cartesianAcceleration;
                dst->xAcceleration=vanetza::asn1::allocate<LongitudinalAcceleration_t>();
                dst->xAcceleration->longitudinalAccelerationValue=a.xAcceleration.value;
                dst->xAcceleration->longitudinalAccelerationConfidence=a.xAcceleration.confidence;
                dst->yAcceleration=vanetza::asn1::allocate<LateralAcceleration_t>();
                dst->yAcceleration->lateralAccelerationValue=a.yAcceleration.value;
                dst->yAcceleration->lateralAccelerationConfidence=a.yAcceleration.confidence;
                if(a.zAcceleration) { dst->zAcceleration=vanetza::asn1::allocate<VerticalAcceleration_t>(); dst->zAcceleration->verticalAccelerationValue=a.zAcceleration->value; dst->zAcceleration->verticalAccelerationConfidence=a.zAcceleration->confidence; }
            } else if(src.acceleration) note("acceleration","non-cartesian acceleration retained in R2 only");
            auto dimension=[&](const Vanetza_ITS2_ObjectDimension_t* a,ObjectDimension_t*& b) {
                if(!a) return;
                if(a->value>=255) { note("dimension","out-of-range/unavailable R2 dimension omitted"); return; }
                b=vanetza::asn1::allocate<ObjectDimension_t>(); b->value=a->value; b->confidence=dimension_confidence(a->confidence);
                if(a->confidence>10 && a->confidence<31) note("dimensionConfidence","outside historical confidence range; original retained");
            };
            dimension(src.objectDimensionX,dst->planarObjectDimension1); dimension(src.objectDimensionY,dst->planarObjectDimension2); dimension(src.objectDimensionZ,dst->verticalObjectDimension);
            if(src.sensorIdList) {
                dst->sensorIDList=vanetza::asn1::allocate<SensorIdList_t>();
                for(int s=0;s<src.sensorIdList->list.count;++s) { auto* value=vanetza::asn1::allocate<Identifier_t>(); *value=*src.sensorIdList->list.array[s]; ASN_SEQUENCE_ADD(dst->sensorIDList,value); }
            }
            if(src.objectAge && *src.objectAge<=1500) { dst->objectAge=vanetza::asn1::allocate<ObjectAge_t>(); *dst->objectAge=*src.objectAge; }
            else if(src.objectAge) note("objectAge","age exceeds historical range; retained in R2 only");
            if(src.classification) for(int c=0;c<src.classification->list.count;++c) {
                const auto& cls=*src.classification->list.array[c];
                auto* old=vanetza::asn1::allocate<ObjectClass_t>();
                bool supported=true; old->confidence=cls.confidence;
                if(cls.objectClass.present==Vanetza_ITS2_ObjectClass_PR_vehicleSubClass) {
                    const std::map<long,long> types={{0,0},{3,1},{4,2},{5,3},{6,4},{7,5},{8,6},{9,7},{10,8},{11,9},{14,11}};
                    auto found=types.find(cls.objectClass.choice.vehicleSubClass);
                    if(found==types.end()) supported=false;
                    else { old->Class.present=ObjectClass__class_PR_vehicle; old->Class.choice.vehicle.type=found->second; old->Class.choice.vehicle.confidence=cls.confidence; }
                } else if(cls.objectClass.present==Vanetza_ITS2_ObjectClass_PR_vruSubClass) {
                    auto kind=cls.objectClass.choice.vruSubClass.present;
                    if(kind==Vanetza_ITS2_VruProfileAndSubprofile_PR_pedestrian || kind==Vanetza_ITS2_VruProfileAndSubprofile_PR_bicyclistAndLightVruVehicle) {
                        old->Class.present=ObjectClass__class_PR_person;
                        long type=1;
                        if(kind==Vanetza_ITS2_VruProfileAndSubprofile_PR_bicyclistAndLightVruVehicle) {
                            long sub=cls.objectClass.choice.vruSubClass.choice.bicyclistAndLightVruVehicle;
                            type=(sub==1 || (sub>=7 && sub<=10))?3:(sub==2?2:(sub==4?5:0));
                        }
                        old->Class.choice.person.type=type; old->Class.choice.person.confidence=cls.confidence;
                        note("vruSubProfile","profile preserved; finer R2 subprofile retained only in source");
                    } else supported=false;
                } else supported=false;
                if(supported) { if(!dst->classification) dst->classification=vanetza::asn1::allocate<ObjectClassDescription_t>(); ASN_SEQUENCE_ADD(dst->classification,old); }
                else { vanetza::asn1::free(asn_DEF_ObjectClass,old); note("classification","unmapped class retained in source R2 only"); }
            }
            if(src.angles || src.zAngularVelocity || src.lowerTriangularCorrelationMatrices || src.objectPerceptionQuality || src.mapPosition)
                note("object_"+std::to_string(id),"angles/angular velocity/covariance/quality/map position retained in R2 only");
            Json object={{"id",id},{"x_cm",dst->xDistance.value},{"y_cm",dst->yDistance.value},
                {"vx_cm_s",dst->xSpeed.value},{"vy_cm_s",dst->ySpeed.value},{"velocity_available",velocity},
                {"measurement_delta_ms",dst->timeOfMeasurement},{"measurement_time_ms",result.reference_time_ms+dst->timeOfMeasurement},
                {"acceleration_present",dst->xAcceleration!=nullptr},{"length_present",dst->planarObjectDimension1!=nullptr},
                {"width_present",dst->planarObjectDimension2!=nullptr},{"classification_present",dst->classification!=nullptr}};
            if(dst->zDistance) object["z_cm"]=dst->zDistance->value;
            result.objects.push_back(object);
        }
    }
    note("coverage","no trustworthy historical sensor FoV conversion; distance check not evaluable");
    if(!result.legacy.validate(error)) throw std::runtime_error("converted historical constraints: "+error);
    return result;
}
// The callback is the ORIGINAL F2MD speedPlausibility(x,y), supplied by CpmChecks.
// Other historical checks have known frame/time/confidence defects: do not
// report a pass/fail for them until their R2 contracts have independent tests.
inline double evaluate(Conversion& conversion,const std::function<double(double,double)>& speed) {
    Json checked=Json::array(),skipped=Json::array(); double anomalies=0;
    auto* list=conversion.legacy->cpm.cpmParameters.perceivedObjectContainer;
    if(list) for(int i=0;i<list->list.count;++i) {
        const auto& object=*list->list.array[i];
        if(conversion.velocity_available.at(object.objectID)) {
            const double result=speed(object.xSpeed.value,object.ySpeed.value);
            if(!std::isfinite(result)) throw std::runtime_error("non-finite F2MD check result");
            checked.push_back({{"id",object.objectID},{"check","speed_plausibility"},{"result",result}});
            anomalies+=result>0;
        } else skipped.push_back({{"id",object.objectID},{"check","speed_plausibility"},{"reason","velocity unavailable"}});
    }
    skipped.push_back({{"check","distance_plausibility"},{"reason","sensor FoV unavailable or not mapped; no fabricated coverage/dimensions"}});
    skipped.push_back({{"check","temporal_consistency"},{"reason","historical checks mix Cartesian speed/angle, integer time and inconsistent units; R2 path not validated"}});
    skipped.push_back({{"check","kalman_consistency"},{"reason","historical confidence/acceleration/coordinate contracts not validated for R2"}});
    conversion.control={{"evaluated",checked},{"non_evaluable",skipped},{"anomalies",anomalies},
        {"complete",false},{"verdict",checked.empty()?"non_evaluable":(anomalies>0?"anomaly_in_evaluated_checks":"no_anomaly_in_evaluated_checks")}};
    return anomalies>0?1.0:0.0;
}
}} // namespace artery::cpm_a2
