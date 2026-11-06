#ifndef ARTERY_CARLAPERCEPTIONSERVICE_H_
#define ARTERY_CARLAPERCEPTIONSERVICE_H_
#include "artery/application/ItsG5BaseService.h"
#include "artery/application/VehicleDataProvider.h"
#include "cpm/PerceptionCpm.h"
#include <omnetpp/simtime.h>
#include <string>
namespace artery {
class Timer;
class CarlaPerceptionService : public ItsG5BaseService {
public:
    void initialize() override;
    void trigger() override;
    void indicate(const vanetza::btp::DataIndication&, std::unique_ptr<vanetza::UpPacket>) override;
    const Timer* getTimer() const;
    void sendCpm(const omnetpp::SimTime&);
private:
    const VehicleDataProvider* mVehicleDataProvider = nullptr;
    const Timer* mTimer = nullptr;
    omnetpp::SimTime mLastCpmTimestamp, mGenCpmMax;
    std::string mJsonPath;
};
}
#endif
