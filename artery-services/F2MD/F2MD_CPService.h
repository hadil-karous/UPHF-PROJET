/*******************************************************************************
 * @author  Jiahao ZHANG
 * @email   jiahao.zhang96@gmail.com
 * @date    09/11/2022
 * @version 2.0
 *
 * TAM (Trusted Autonomous Mobility)
 * Copyright (c) 2013, 2021 Institut de Recherche Technologique SystemX
 * All rights reserved.
 *******************************************************************************/

#ifndef ARTERY_F2MD_CPSERVICE_H_
#define ARTERY_F2MD_CPSERVICE_H_

#include "F2MD_CPParameters.h"
#include "F2MD_CPFacility.h"
#include "TemporalPlausibility.h"

#include "artery/application/ItsG5BaseService.h"
#include "artery/traci/VehicleController.h"
#include "artery/utility/Channel.h"
#include "artery/utility/Geometry.h"
#include "artery/envmod/LocalEnvironmentModel.h"
#include "artery/envmod/GlobalEnvironmentModel.h"
#include "artery/envmod/EnvironmentModelObject.h"
#include "artery/envmod/service/EnvmodPrinter.h"
#include "artery/application/F2MD/mdFiles/mdPCPolicies/PCPolicyCPM.h"
#include <inet/linklayer/ieee80211/mac/Ieee80211Mac.h>
#include <vanetza/asn1/cpm.hpp>
#include <vanetza/btp/data_interface.hpp>
#include <vanetza/units/angle.hpp>
#include <vanetza/units/velocity.hpp>
#include <vanetza/geonet/pdu.hpp>
#include <vanetza/geonet/pdu_conversion.hpp>
#include <vanetza/geonet/pdu_variant.hpp>
#include <vanetza/net/osi_layer.hpp>
#include <omnetpp/simtime.h>
#include <iostream>
#include <fstream>
#include "mdFiles/mdSupport/JsonWriter.h"
#include "mdFiles/mdBase/CpmCheckList.h"
#include "mdFiles/mdBase/ExtendPerceptionTable.h"

namespace traci { class VehicleController; }

static list<double> stationID;

namespace artery
{


class Timer;
class VehicleDataProvider;

class F2MD_CPService : public ItsG5BaseService
{
    public:
        F2MD_CPService();
        void initialize() override;
        void indicate(const vanetza::btp::DataIndication&, std::unique_ptr<vanetza::UpPacket>) override;
        void trigger() override;
        void finish() override;

    protected:
        std::string printRXCpmtoJson(const vanetza::asn1::Cpm& msg, double checkfailed);
    double mLastCheckfailed = 0.0;
        std::string printTXCpmtoJson(const vanetza::asn1::Cpm& msg) ;
        std::string printperceivedlisttoJson(const std::string& title, const TrackedObjectsFilterRange& objs);
        
    private:
        F2MD_CPParameters CPparams;
        F2MD_CPFacility mF2MDFacility;
        cpm_a3::Engine mTemporalHistory;

        const VehicleDataProvider* mVehicleDataProvider = nullptr;
        const traci::VehicleController* mVehicleController = nullptr;
		const Timer* mTimer = nullptr;
        omnetpp::SimTime mLastCpmTimestamp;
        bool mCpmTxFailed = false;
		omnetpp::SimTime mGenCpmMax;
		omnetpp::SimTime mGenCpm;
        bool mFixedRate;
        const LocalEnvironmentModel* mlocalEnvmod;
        GlobalEnvironmentModel* mglobleEnvmod;
        EnvmodPrinter* mEnvmodprint;
        ofstream outputfilelog;
        ofstream outputjsonfilecpm;
        ofstream outputjsonfilelem;
        ofstream outputjsonfilecpmEmit;


        JsonWriter jwritelem;
        JsonWriter jwritecpmRX;
        JsonWriter jwritecpmTX;
        
        ExtendPerceptionTable mExtendPerceptionTable;
        CpmCheckList mCpmCheckList;

        const std::string SUMO_id;
        pseudoChangeTypes::PseudoChange myPcType;
        PCPolicyCPM mPCPolicyCPM;
        unsigned long myPseudonym;
        libsumo::TraCIPosition coordPos;
        int pseudoNum;
        inet::MACAddress myMacId;
        cModule* node;

        using ItsG5BaseService::getFacilities;
        const Timer* getTimer() const;
		void sendCpm(const omnetpp::SimTime&);
        vanetza::asn1::Cpm createCollectivePerceptionMessage(const VehicleDataProvider&, uint16_t genDeltaTime, const LocalEnvironmentModel&);

        void checkReception(const vanetza::asn1::Cpm&);
        void initParams();

        std::string printFinalTagtoJson();


};


} // namespace artery

#endif
