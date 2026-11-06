#include <vanetza/asn1/cpm.hpp>
#include <vanetza/asn1/its/r2/WrappedCpmContainer.h>
#include <vanetza/asn1/its/r2/PerceivedObject.h>
#include <vanetza/asn1/support/per_decoder.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <iterator>

using json = nlohmann::json;
int main(int argc, char** argv) {
    if (argc != 3 && argc != 4) return 2;
    std::ifstream input(argv[2], std::ios::binary);
    if (!input) return 2;
    vanetza::ByteBuffer bytes((std::istreambuf_iterator<char>(input)), {});
    json out;
    out["format"] = argv[1]; out["input_bytes"] = bytes.size();
    void* ptr = nullptr;
    bool r2 = std::string(argv[1]) == "r2";
    auto& desc = r2 ? asn_DEF_Vanetza_ITS2_CollectivePerceptionMessage : asn_DEF_CPM;
    auto result = uper_decode_complete(nullptr, &desc, &ptr, bytes.data(), bytes.size());
    out["decode_code"] = result.code;
    out["consumed_bytes"] = result.consumed;
    out["decoded"] = result.code == RC_OK;
    std::string error;
    if (result.code == RC_OK) {
        if (argc == 4) {
            FILE* dump = std::fopen(argv[3], "w");
            if (!dump) return 2;
            vanetza::asn1::print(dump, desc, ptr);
            std::fclose(dump);
        }
        out["valid"] = vanetza::asn1::validate(desc, ptr, error);
        out["validation_error"] = error;
        if (r2) {
            auto* msg = static_cast<Vanetza_ITS2_CollectivePerceptionMessage_t*>(ptr);
            out["station_id"] = msg->header.stationId;
            long time = 0; asn_INTEGER2long(&msg->payload.managementContainer.referenceTime, &time);
            out["reference_time_ms"] = time;
            auto& pos = msg->payload.managementContainer.referencePosition;
            out["reference"] = {{"latitude", pos.latitude / 1e7}, {"longitude", pos.longitude / 1e7}};
            out["containers"] = json::array(); out["objects"] = json::array();
            for (int i = 0; i < msg->payload.cpmContainers.list.count; ++i) {
                auto& c = *msg->payload.cpmContainers.list.array[i];
                out["containers"].push_back(c.containerId);
                if (c.containerData.present != Vanetza_ITS2_WrappedCpmContainer__containerData_PR_PerceivedObjectContainer) continue;
                auto& list = c.containerData.choice.PerceivedObjectContainer.perceivedObjects.list;
                for (int k = 0; k < list.count; ++k) {
                    auto& o = *list.array[k];
                    json item = {{"x_m", o.position.xCoordinate.value / 100.0}, {"y_m", o.position.yCoordinate.value / 100.0}, {"measurement_delta_ms", o.measurementDeltaTime}, {"id", o.objectId ? json(*o.objectId) : json(nullptr)}, {"acceleration_present", o.acceleration != nullptr}, {"length_present", o.objectDimensionX != nullptr}, {"width_present", o.objectDimensionY != nullptr}, {"sensor_ids_present", o.sensorIdList != nullptr}};
                    if (o.position.zCoordinate) item["z_m"] = o.position.zCoordinate->value / 100.0;
                    if (o.velocity && o.velocity->present == Vanetza_ITS2_Velocity3dWithConfidence_PR_cartesianVelocity) {
                        item["vx_m_s"] = o.velocity->choice.cartesianVelocity.xVelocity.value / 100.0;
                        item["vy_m_s"] = o.velocity->choice.cartesianVelocity.yVelocity.value / 100.0;
                    }
                    if (o.classification && o.classification->list.count) {
                        auto& cl = o.classification->list.array[0]->objectClass;
                        item["class_choice"] = cl.present;
                        if (cl.present == Vanetza_ITS2_ObjectClass_PR_vehicleSubClass) item["vehicle_class"] = cl.choice.vehicleSubClass;
                        if (cl.present == Vanetza_ITS2_ObjectClass_PR_vruSubClass) item["vru_choice"] = cl.choice.vruSubClass.present;
                    }
                    out["objects"].push_back(item);
                }
            }
        }
    }
    if (ptr) vanetza::asn1::free(desc, ptr);
    std::cout << out.dump(2) << std::endl;
    return result.code == RC_OK ? 0 : 1;
}
