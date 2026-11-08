#pragma once
#include "R2ToLegacy.h"
#include "TemporalPlausibility.h"
#include <set>

namespace artery { namespace cpm_a3 {
// Preserve the original ASN.1 payload and model R2 objects without R1 narrowing.
inline cpm_a2::Conversion prepare(const vanetza::asn1::r2::Cpm& r2,Context& context) {
    auto converted=cpm_a2::convert(r2,true);
    context.message.station=r2->header.stationId;
    context.message.reference_ms=converted.reference_time_ms;
    context.message.objects.clear();
    const auto& reference=r2->payload.managementContainer.referencePosition;
    for(int c=0;c<r2->payload.cpmContainers.list.count;++c) {
        const auto& container=r2->payload.cpmContainers.list.array[c]->containerData;
        if(container.present!=Vanetza_ITS2_WrappedCpmContainer__containerData_PR_PerceivedObjectContainer) continue;
        const auto& poc=container.choice.PerceivedObjectContainer;
        if(poc.numberOfPerceivedObjects!=poc.perceivedObjects.list.count) throw std::runtime_error("R2 object count mismatch");
        for(int i=0;i<poc.perceivedObjects.list.count;++i) {
            const auto& po=*poc.perceivedObjects.list.array[i]; Object o;
            if(po.objectId) o.id=static_cast<std::uint16_t>(*po.objectId);
            o.delta_ms=po.measurementDeltaTime;
            o.measurement_ms=context.message.reference_ms+o.delta_ms; // signed image/A1 contract
            o.x_cm=po.position.xCoordinate.value; o.y_cm=po.position.yCoordinate.value;
            o.position_available=o.x_cm!=-131072 && o.x_cm!=131071 && o.y_cm!=-131072 && o.y_cm!=131071;
            if(reference.latitude>=-900000000 && reference.latitude<=900000000 &&
                reference.longitude>=-1800000000 && reference.longitude<=1800000000) {
                o.latitude_deg=reference.latitude/1e7; o.longitude_deg=reference.longitude/1e7;
            }
            if(po.velocity && po.velocity->present==Vanetza_ITS2_Velocity3dWithConfidence_PR_cartesianVelocity) {
                const auto& v=po.velocity->choice.cartesianVelocity;
                o.vx_cm_s=v.xVelocity.value; o.vy_cm_s=v.yVelocity.value;
                o.velocity_available=o.vx_cm_s>-16383 && o.vx_cm_s<16382 && o.vy_cm_s>-16383 && o.vy_cm_s<16382;
            }
            Json summary={{"id",o.id?Json(*o.id):Json(nullptr)},{"measurement_time_ms",o.measurement_ms},
                {"measurement_delta_ms",o.delta_ms},{"x_cm",o.x_cm},{"y_cm",o.y_cm},{"position_available",o.position_available},
                {"velocity_available",o.velocity_available},{"vx_cm_s",o.velocity_available?Json(o.vx_cm_s):Json(nullptr)},
                {"vy_cm_s",o.velocity_available?Json(o.vy_cm_s):Json(nullptr)},
                {"classification_present",po.classification!=nullptr},{"acceleration_present",po.acceleration!=nullptr},
                {"dimensions_present",po.objectDimensionX || po.objectDimensionY || po.objectDimensionZ},
                {"sensor_ids_present",po.sensorIdList!=nullptr}};
            converted.objects.push_back(summary); context.message.objects.push_back(o);
        }
    }
    converted.temporal_context=&context;
    return converted;
}
}} // namespace artery::cpm_a3
