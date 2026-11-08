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

#include "artery/application/CpmObject.h"
#include "F2MD_CPService.h"
#include "artery/application/Asn1PacketVisitor.h"
#include "artery/application/MultiChannelPolicy.h"
#include "artery/application/VehicleDataProvider.h"
#include "artery/utility/simtime_cast.h"
#include "veins/base/utils/Coord.h"
#include "artery/envmod/EnvironmentModelObject.h"
#include "artery/envmod/sensor/Sensor.h"

#include <boost/units/cmath.hpp>
#include <boost/units/systems/si/prefixes.hpp>
#include <omnetpp/cexception.h>
#include <vanetza/btp/ports.hpp>
#include <vanetza/facilities/cam_functions.hpp>
#include <chrono>
#include "R2ToLegacy.h"
#include "R2Temporal.h"
#include <filesystem>
#include <cstdlib>


std::map<int,int> PseudoID2ArteryID;

namespace artery
{

using namespace omnetpp;
Define_Module(F2MD_CPService)

static const simsignal_t scSignalCpmReceived = cComponent::registerSignal("CpmReceived");
static const simsignal_t scSignalCpmSent = cComponent::registerSignal("CpmSent");

F2MD_CPService::F2MD_CPService(){
}

/**
   *  @brief Initialise CPM Service and CPM Facility for further F2MD Processing
*/
void F2MD_CPService::initialize()
{
    // std::cout << "entering initialize in CPService at "<<SIMTIME_STR(simTime())<<std::endl;

    ItsG5BaseService::initialize();
    mVehicleDataProvider = &getFacilities().get_const<VehicleDataProvider>();
    mVehicleController = &getFacilities().get_const<traci::VehicleController>();
    mTimer = &getFacilities().get_const<Timer>();
    mlocalEnvmod = &getFacilities().get_const<LocalEnvironmentModel>();
    mglobleEnvmod = &getFacilities().get_mutable<GlobalEnvironmentModel>();
    std::shared_ptr<const traci::API> mTraci = mVehicleController->getTraCI();
    mTraci->vehicle.setSpeedMode(mVehicleController->getVehicleId(), 0);
    mTraci->vehicle.setLaneChangeMode(mVehicleController->getVehicleId(), 0);

    mGenCpmMax = par("maxInterval");
    mFixedRate = par("fixedRate");
    mLastCpmTimestamp = simTime();
    initParams();

    // generation rate boundaries
	mGenCpm = mGenCpmMax;
    int myId = mVehicleDataProvider->getStationId();
    int attackType = mF2MDFacility.getAttackType();

    // Initialize Pseudonym Change Policy
    myPcType = CPparams.PC_TYPE;
    pseudoNum = 0;
    //Node Module Acces and Mac Address
    node = inet::findContainingNode(this);

    myMacId = inet::getModuleFromPar<inet::ieee80211::Ieee80211Mac>(par("pathToMacModule"),node)->getAddress();
    auto SUMO_id = mVehicleController->getVehicleId();
    auto vehicle_api = mVehicleController->getTraCI()->vehicle;
    auto coordPosInit = vehicle_api.getPosition(SUMO_id);
    mPCPolicyCPM = PCPolicyCPM(coordPosInit, &CPparams);
    mPCPolicyCPM.setCurPosition(&coordPosInit);
    mPCPolicyCPM.setMyId(&myMacId);
    mPCPolicyCPM.setMyPseudonym(&myPseudonym);
    mPCPolicyCPM.setPseudoNum(&pseudoNum);
    myPseudonym = mPCPolicyCPM.getNextPseudonym()  % 4294967295;
    myPseudonym = myPseudonym % 4294967295;
    if(PseudoID2ArteryID.find(myPseudonym) == PseudoID2ArteryID.end()){
        PseudoID2ArteryID.insert(std::pair<int,int>(myPseudonym,myId));
    }

    // ------ Initialization of F2MD Module ------ Start
    mF2MDFacility = F2MD_CPFacility(mVehicleDataProvider, mVehicleController, CPparams, &myPseudonym);
    mF2MDFacility.initialize();

    mExtendPerceptionTable = ExtendPerceptionTable();
    // ------ Initialization of F2MD Module ------ End

    string str_id = to_string(myId);
    string outlogfile_name = "output/Log/";
    outlogfile_name.append(cpAttackTypes::AttackNames[CPparams.CP_LOCAL_ATTACK_TYPE]);
    if(CPparams.KeepSameID == true){
        outlogfile_name.append("_KeepSameID");
    }
    struct stat info_log;
    if ((stat(outlogfile_name.c_str(), &info_log) != 0) || !(info_log.st_mode & S_IFDIR)) {
        mkdir(outlogfile_name.c_str(), 0777);
    }
    outlogfile_name.append("/log_vehicle_");    
    outlogfile_name.append(str_id);
    outputfilelog.open(outlogfile_name,ios::out);

    // For Json
    string suffix = ".json";

    string outjsonfilecpm_name = "output/GENUINE/CPM/RX/";
    outjsonfilecpm_name.append(cpAttackTypes::AttackNames[CPparams.CP_LOCAL_ATTACK_TYPE]);
    if(CPparams.KeepSameID == true){
        outjsonfilecpm_name.append("_KeepSameID");
    }
    struct stat info_rx;
    if ((stat(outjsonfilecpm_name.c_str(), &info_rx) != 0) || !(info_rx.st_mode & S_IFDIR)) {
        mkdir(outjsonfilecpm_name.c_str(), 0777);
    }
    outjsonfilecpm_name.append("/logjson_cpm_rx");
    outjsonfilecpm_name.append(str_id);
    outjsonfilecpm_name.append (suffix);
    outputjsonfilecpm.open(outjsonfilecpm_name,ios::out);
    jwritecpmRX.openJsonElementList("CPM_RX");


    string outjsonfilecpmEmit_name = "output/GENUINE/CPM/TX/";
    outjsonfilecpmEmit_name.append(cpAttackTypes::AttackNames[CPparams.CP_LOCAL_ATTACK_TYPE]);
    if(CPparams.KeepSameID == true){
        outjsonfilecpmEmit_name.append("_KeepSameID");
    }
    struct stat info_tx;
    if ((stat(outjsonfilecpmEmit_name.c_str(), &info_tx) != 0) || !(info_tx.st_mode & S_IFDIR)) {
        mkdir(outjsonfilecpmEmit_name.c_str(), 0777);
    }
    outjsonfilecpmEmit_name.append("/logjson_cpm_tx");
    outjsonfilecpmEmit_name.append(str_id);
    outjsonfilecpmEmit_name.append (suffix);
    outputjsonfilecpmEmit.open(outjsonfilecpmEmit_name,ios::out);
    jwritecpmTX.openJsonElementList("CPM_TX");


    // Ground Truth
    string outlemjsonfile_name = "output/GENUINE/LP/";
    outlemjsonfile_name.append(cpAttackTypes::AttackNames[CPparams.CP_LOCAL_ATTACK_TYPE]);
    if(CPparams.KeepSameID == true){
        outlemjsonfile_name.append("_KeepSameID");
    }
    struct stat info_lp;
    if ((stat(outlemjsonfile_name.c_str(), &info_lp) != 0) || !(info_lp.st_mode & S_IFDIR)) {
        mkdir(outlemjsonfile_name.c_str(), 0777);
    }
    outlemjsonfile_name.append("/logjson_lp");
    outlemjsonfile_name.append(str_id);
    outlemjsonfile_name.append (suffix);
    outputjsonfilelem.open(outlemjsonfile_name,ios::out);
    jwritelem.openJsonElementList("LP");
}



/**
   *  @brief  called periodically by the middleware. UpdateFreq is defined in omnetpp.ini
*/
void F2MD_CPService::trigger()
{
    if (std::getenv("EXFMD_F2MD_RX_ONLY")) return;  
    SimTime& T_GenCpm = mGenCpm;
	const SimTime& T_GenCpmMax = mGenCpmMax;
    const SimTime T_elapsed = simTime() - mLastCpmTimestamp;


    // The condition needs to be completed
    if (T_elapsed >= T_GenCpmMax)
    {
        if (!mCpmTxFailed) {
            try {
                sendCpm(simTime());
            } catch(const std::bad_alloc& e) {
                std::cerr << "trigger sendCpm bad_alloc (disabling TX)" << std::endl;
                mCpmTxFailed = true;
            } catch(const std::length_error& e) {
                std::cerr << "trigger sendCpm length_error (disabling TX)" << std::endl;
                mCpmTxFailed = true;
            } catch(const std::exception& e) {
                std::cerr << "trigger sendCpm failed: " << e.what() << std::endl;
                mCpmTxFailed = true;
            } catch(...) {
                std::cerr << "trigger sendCpm unknown" << std::endl;
                mCpmTxFailed = true;
            }
        }
        mExtendPerceptionTable.updateTable(simTime().inUnit(SIMTIME_MS));
    }
}


/**
   *  @brief  called by the middleware each time a CPM is received by this node.
*/
namespace {
struct R2ApplicationBytes : boost::static_visitor<vanetza::ByteBuffer> {
    vanetza::ByteBuffer operator()(vanetza::ChunkPacket& packet) const {
        vanetza::ByteBuffer bytes;
        packet[vanetza::OsiLayer::Application].convert(bytes);
        return bytes;
    }
    vanetza::ByteBuffer operator()(vanetza::CohesivePacket& packet) const {
        const auto range=packet[vanetza::OsiLayer::Application];
        return vanetza::ByteBuffer(range.begin(),range.end());
    }
};
}
void F2MD_CPService::indicate(const vanetza::btp::DataIndication& indication, std::unique_ptr<vanetza::UpPacket> packet)
{
    using cpm_a2::Json;
    static unsigned long serial=0;
    const auto event=++serial;
    const auto receiver=mVehicleDataProvider->getStationId();
    auto emit=[&](Json record) {
        record["event_id"]=event; record["receiver"]=receiver;
        record["simulation_time_s"]=simTime().dbl();
        const char* directory=std::getenv("EXFMD_A3_DIR");
        if(!directory) directory=std::getenv("EXFMD_A2_DIR");
        if(directory) {
            std::filesystem::create_directories(directory);
            std::ofstream stream(std::filesystem::path(directory)/("receiver-"+std::to_string(receiver)+".jsonl"),std::ios::app);
            if(!(stream << record.dump() << std::endl)) throw std::runtime_error("cannot write A2 event");
        }
        std::cout << (std::getenv("EXFMD_A3_TEMPORAL")?"F2MD_A3 ":"F2MD_A2 ") << record.dump() << std::endl;
    };
    emit({{"stage","receive"},{"status","ok"}});
    std::string stage="decode",sourceHex;
    try {
        const auto bytes=boost::apply_visitor(R2ApplicationBytes(),*packet);
        sourceHex=cpm_a2::hex(bytes);
        auto r2=cpm_a2::decode(bytes); // always decode bytes; no typed-packet shortcut
        emit({{"stage","decode"},{"status","ok"},{"source_r2_hex",cpm_a2::hex(bytes)}});
        stage="convert";
        cpm_a3::Context temporal;
        temporal.engine=&mTemporalHistory; temporal.receiver=receiver;
        temporal.receive_ms=countTaiMilliseconds(mTimer->getCurrentTime());
        auto converted=std::getenv("EXFMD_A3_TEMPORAL")?cpm_a3::prepare(r2,temporal):cpm_a2::convert(r2);
        emit({{"stage","convert"},{"status","ok"},{"station_id",converted.legacy->header.stationID},
            {"reference_time_ms",converted.reference_time_ms},{"legacy_delta_ms",converted.legacy->cpm.generationDeltaTime},
            {"objects",converted.objects},{"conversion_notes",converted.notes},
            {"legacy_hex",cpm_a2::hex(converted.legacy.encode())}});
        stage="control";
        cpm_a2::Scope scope(converted);
        mCpmCheckList.resetAll();
        const double result=mF2MDFacility.onCPM(converted.legacy,indication.source_position.gn_addr.mid(),mCpmCheckList,PseudoID2ArteryID);
        if(converted.control.empty()) throw std::runtime_error("R2 control policy was not executed");
        emit({{"stage","control"},{"status",converted.control["evaluated"].empty()?"non_evaluable":"partial"},
            {"result",result},{"checks",converted.control},
            {"facility_called",temporal.facility_called},{"temporal_checks_called",temporal.checks_called}});
        emit({{"stage","non_evaluable"},{"status","partial"},{"checks",converted.control["non_evaluable"]}});
        // Do not route a partial/unknown verdict into the historical Genuine log
        // or its alert writer. The structured A2 events are the authoritative result.
    } catch(const cpm_a2::Unsupported& error) {
        emit({{"stage",stage},{"status","non_evaluable"},{"reason",error.what()},{"source_r2_hex",sourceHex}});
    } catch(const std::exception& error) {
        emit({{"stage",stage},{"status",std::getenv("EXFMD_A3_TEMPORAL")?"technical_error":"error"},{"reason",error.what()},{"source_r2_hex",sourceHex}});
    } catch(...) {
        emit({{"stage",stage},{"status",std::getenv("EXFMD_A3_TEMPORAL")?"technical_error":"error"},{"reason","unknown technical exception"}});
    }
}

/**
   *  @brief  print in QtEnv what is contained in the cpm received. Useful for debugging.
   *  @param vanetza::asn1::Cpm& cpm received
*/
void F2MD_CPService::checkReception(const vanetza::asn1::Cpm& msg){

    auto currentTime = simTime().inUnit(SIMTIME_MS);
    mExtendPerceptionTable.updateTable(&msg,currentTime);

    auto& allObjects = mlocalEnvmod->allObjects();
    jwritecpmRX.addTagToElement("CPM_RX", printRXCpmtoJson(msg, mLastCheckfailed));
    // Real-time alert file for detection bridge
    if (mLastCheckfailed > 0) {
        std::string alertFile = "output/GENUINE/CPM/RX/";
        alertFile.append(cpAttackTypes::AttackNames[CPparams.CP_LOCAL_ATTACK_TYPE]);
        alertFile.append("/alert_");
        alertFile.append(std::to_string(simTime().inUnit(SIMTIME_MS)));
        alertFile.append(".json");
        std::ofstream alert(alertFile);
        if (alert.is_open()) {
            alert << "{\"checkfailed\": 1.0, \"simtime\": " << simTime().dbl() << "}" << std::endl;
            alert.close();
        }
    }
    // jwritelem.addTagToElement("LP",printperceivedlisttoJson("Radar Sensor Object List", filterBySensorCategory(allObjects, "Radar")));
}



const Timer* F2MD_CPService::getTimer() const
{
    return mTimer;
}


/**
   *  @brief  create, fill, and send a cpm with correct informations
   *  @param simTime_t current time
*/
void F2MD_CPService::sendCpm(const SimTime& T_now)
{

    uint16_t genDeltaTimeMod = countTaiMilliseconds(mTimer->getTimeFor(mVehicleDataProvider->updated()));

    // Create a new CPM
    vanetza::asn1::Cpm cpm;
    try {
        cpm = createCollectivePerceptionMessage(*mVehicleDataProvider, genDeltaTimeMod,*mlocalEnvmod);
    } catch(const std::exception& e) {
        std::cerr << "createCPM failed: " << e.what() << std::endl;
        mCpmTxFailed = true;
        return;
    }
    mLastCpmTimestamp = T_now;

    // print each emitted CPM messages.
    try { jwritecpmTX.addTagToElement("CPM_TX", printTXCpmtoJson(cpm)); } catch(const std::exception& e) { std::cerr << "printTXCpmtoJson failed: " << e.what() << std::endl; } catch(...) { std::cerr << "printTXCpmtoJson unknown error" << std::endl; }
    

    using namespace vanetza;
	btp::DataRequestB request;
	request.destination_port = btp::ports::CPM;
	request.gn.its_aid = aid::CP;
	request.gn.transport_type = geonet::TransportType::SHB;
	request.gn.maximum_lifetime = geonet::Lifetime { geonet::Lifetime::Base::One_Second, 1 };
	request.gn.traffic_class.tc_id(static_cast<unsigned>(dcc::Profile::DP2));
	request.gn.communication_profile = geonet::CommunicationProfile::ITS_G5;

	CpmObject obj(std::move(cpm));
    // validate removed - hardcoded valid fields
	std::unique_ptr<geonet::DownPacket> payload { new geonet::DownPacket() };
    using CpmByteBuffer = convertible::byte_buffer_impl<vanetza::asn1::Cpm>;
    std::unique_ptr<convertible::byte_buffer> buffer { new CpmByteBuffer(obj.shared_ptr()) };
    payload->layer(OsiLayer::Application) = std::move(buffer);

    // Pre-test encoding before sending
    try {
        auto testbuf = obj.shared_ptr()->encode();
    } catch(const std::exception& e) {
        std::cerr << "sendCpm pre-encode failed: " << e.what() << std::endl;
        mCpmTxFailed = true;
        return;
    } catch(...) {
        std::cerr << "sendCpm pre-encode unknown" << std::endl;
        mCpmTxFailed = true;
        return;
    }
    // Send the CPM to lower layers
    try {
	this->request(request, std::move(payload));
    } catch(const std::exception& e) { std::cerr << "sendCpm request failed: " << e.what() << std::endl; }

    // emit(scSignalCpmSent, &obj); // TEMP DISABLED - crashes CpmSensor with POC
    
}

/**
   *  @brief  create and fill a cpm with correct informations
   *  @param VehicleDataProvider& my vehicle data provider
   *  @param uint16_t genDeltaTime
   *  @param LocalEnvironmentModel& my local env model
*/
vanetza::asn1::Cpm F2MD_CPService::createCollectivePerceptionMessage(const VehicleDataProvider& vdp, uint16_t genDeltaTime, const LocalEnvironmentModel& lem)
{
    // using vanetza::facilities::distance;

    vanetza::asn1::Cpm message;
    ItsPduHeader_t& header = (*message).header;
	header.protocolVersion = 2;
	header.messageID = 14;

    // Note: with pseudonym change
    // Station ID interval: [0, 4294967295]
    // The ITS-S ID may be a pseudonym. It may change over space and/or over time.
    if (CPparams.EnablePC) {
        auto ArteryID = vdp.getStationId() % 4294967295;
        auto SUMO_id = mVehicleController->getVehicleId();
        auto vehicle_api = mVehicleController->getTraCI()->vehicle;
        coordPos = vehicle_api.getPosition(SUMO_id);
        mPCPolicyCPM.setCurPosition(&coordPos);
        mPCPolicyCPM.checkPseudonymChange(CPparams.PC_TYPE);
        myPseudonym = myPseudonym % 4294967295;
        if(PseudoID2ArteryID.find(myPseudonym) == PseudoID2ArteryID.end()){
            PseudoID2ArteryID.insert(std::pair<int,int>(myPseudonym,ArteryID));
        }
    }else{
        myPseudonym = vdp.getStationId() % 4294967295; // artery allocated ID
    }

    // std::cout << CPparams.EnablePC << endl;

    header.stationID = myPseudonym;


    CollectivePerceptionMessage_t& cpmMsg = (*message).cpm;
    // Create Management Container
    CpmManagementContainer_t& management = (*message).cpm.cpmParameters.managementContainer;
    long referenceTime = countTaiMilliseconds(mTimer->getCurrentTime());
    int ret = 0;
    (*message).cpm.generationDeltaTime = (GenerationDeltaTime_t)(referenceTime % 65536); // r1: plain long, modulo wrap
    assert(ret == 0);
    management.referencePosition.altitude.altitudeValue = AltitudeValue_unavailable;
    management.referencePosition.altitude.altitudeConfidence = AltitudeConfidence_unavailable;
    long mlatitude = std::round(vdp.latitude().value() * 1e7);
    long mlongitude = std::round(vdp.longitude().value() * 1e7);
    if(mlatitude > (-9e8) && mlatitude < 9e8+1){
        management.referencePosition.latitude = mlatitude;
    }else{
        management.referencePosition.latitude = Latitude_unavailable;
    }
    if(mlongitude > (-18e8) && mlongitude < 18e8+1){
        management.referencePosition.longitude = mlongitude;
    }else if(mlongitude == -18e8){
        management.referencePosition.longitude = Longitude_unavailable;
    }else{
        management.referencePosition.longitude = Longitude_unavailable;
    }

    management.referencePosition.positionConfidenceEllipse.semiMinorConfidence = SemiAxisLength_unavailable;
    management.referencePosition.positionConfidenceEllipse.semiMajorConfidence = SemiAxisLength_unavailable;
    management.referencePosition.positionConfidenceEllipse.semiMajorOrientation = HeadingValue_unavailable;

    // ---- EGO ATTACK INJECTION ----
    if (mF2MDFacility.getMbType() == mbTypes::LocalAttacker && simTime().dbl() > CPparams.START_CPM_ATTACK) {
        cpAttackTypes::Attacks atkType = CPparams.CP_LOCAL_ATTACK_TYPE;
        // ConstPos / SingleConstDist: freeze position at a fixed offset
        if (atkType == cpAttackTypes::SingleConstDist || atkType == cpAttackTypes::MultiConstDist) {
            management.referencePosition.latitude  = std::round((vdp.latitude().value()  + 0.005) * 1e7);
            management.referencePosition.longitude = std::round((vdp.longitude().value() + 0.005) * 1e7);
        }
        // RandomPos: add random offset
        else if (atkType == cpAttackTypes::SingleRandomDist || atkType == cpAttackTypes::MultiRandomDist) {
            double offsetLat = ((double)rand()/RAND_MAX - 0.5) * 0.02;
            double offsetLon = ((double)rand()/RAND_MAX - 0.5) * 0.02;
            management.referencePosition.latitude  = std::round((vdp.latitude().value()  + offsetLat) * 1e7);
            management.referencePosition.longitude = std::round((vdp.longitude().value() + offsetLon) * 1e7);
        }
        // ConstSpeed / SingleConstSpeed: will be applied to originatingVehicleContainer heading/speed below
    }
    // ---- END EGO ATTACK ----

    // add all containers
    // -----------------------------------
    // Create OriginatingVehicle Container 
    // -----------------------------------
    (*message).cpm.cpmParameters.stationDataContainer = vanetza::asn1::allocate<StationDataContainer_t>();
    (*message).cpm.cpmParameters.stationDataContainer->present = StationDataContainer_PR_originatingVehicleContainer;
    OriginatingVehicleContainer_t& mOriginatingVehicleContainer = (*message).cpm.cpmParameters.stationDataContainer->choice.originatingVehicleContainer;
    // Set mandatory Heading field in OriginatingVehicleContainer
    auto headingValue = std::round(vdp.heading().value() * 1800 / PI);
    if(headingValue >= 0 && headingValue <= 3600){
        mOriginatingVehicleContainer.heading.headingValue = (HeadingValue_t)headingValue;
    } else {
        mOriginatingVehicleContainer.heading.headingValue = HeadingValue_unavailable;
    }
    mOriginatingVehicleContainer.heading.headingConfidence = HeadingConfidence_unavailable;
    // Set mandatory Speed field
    mOriginatingVehicleContainer.speed.speedValue = SpeedValue_unavailable;
    mOriginatingVehicleContainer.speed.speedConfidence = SpeedConfidence_unavailable;
    // ---- EGO SPEED ATTACK ----
    if (mF2MDFacility.getMbType() == mbTypes::LocalAttacker && simTime().dbl() > CPparams.START_CPM_ATTACK) {
        cpAttackTypes::Attacks atkType = CPparams.CP_LOCAL_ATTACK_TYPE;
        if (atkType == cpAttackTypes::SingleConstSpeed || atkType == cpAttackTypes::MultiConstSpeed) {
            mOriginatingVehicleContainer.speed.speedValue = 0; // freeze speed to 0
        } else if (atkType == cpAttackTypes::SingleRandomSpeed || atkType == cpAttackTypes::MultiRandomSpeed) {
            mOriginatingVehicleContainer.speed.speedValue = rand() % 16383; // random speed
        }
    }
    // ---- END EGO SPEED ATTACK ----
    // Set mandatory DriveDirection field
    mOriginatingVehicleContainer.driveDirection = DriveDirection_forward;

    // orientationAngle != heading according to EN 302 890-2, but in the simulateur, we consider orientationAngle = heading
    // Wgs84AngleValue, Unit: 0,1 degrees
    auto orientationAngleValue = std::round(vdp.heading().value() * 1800 / PI);
    mOriginatingVehicleContainer.vehicleOrientationAngle = nullptr; // OPTIONAL - skip
    if( (orientationAngleValue >= 0) && (orientationAngleValue <= 3600)){    //
        //mOriginatingVehicleContainer.vehicleOrientationAngle->value = orientationAngleValue; // heading(), radian from north, clockwise
    }else{    //
        //mOriginatingVehicleContainer.vehicleOrientationAngle->value = WGS84AngleValue_unavailable;
    }
    // cout << "stationID::" << vdp.getStationId() << "; orientationAngleValue::" << orientationAngleValue << endl;    //

    //mOriginatingVehicleContainer.vehicleOrientationAngle->confidence = AngleConfidence_unavailable;
    // --------------------------------
    // Create PerceivedObject Container
    // --------------------------------
    // the dynamic pereceived list
    const auto& objects = lem.allObjects();
    int countLostTracingNum=0;
    if(objects.size()>0){ // POC enabled
        int pocCount = 0;
        (*message).cpm.cpmParameters.perceivedObjectContainer = vanetza::asn1::allocate<PerceivedObjectContainer_t>();
        PerceivedObjectContainer_t& mPerceivedObjectContainer = *(*message).cpm.cpmParameters.perceivedObjectContainer;
        // mPerceivedObjectContainer.perceivedObjects = vanetza::asn1::allocate<PerceivedObjects_t>();
        for (const auto& obj : objects){ 
            std::weak_ptr<EnvironmentModelObject> obj_ptr = obj.first;  
            if (obj_ptr.expired()){
                countLostTracingNum++;
                continue; /*< objects remain in tracking briefly after leaving simulation */
            }
            if(pocCount >= 1) { countLostTracingNum++; continue; } // LIMIT 1 object
            pocCount++;
            PerceivedObject_t* object = vanetza::asn1::allocate<PerceivedObject_t>();
            auto objPos = obj_ptr.lock()->getCentrePoint();
            auto egoPos = mVehicleDataProvider->position();
            double dx = (objPos.x - egoPos.x).value() * 100.0; // cm
            double dy = (objPos.y - egoPos.y).value() * 100.0; // cm
            // clamp to ASN.1 r1 range [-132768..132767]
            dx = std::max(-132768.0, std::min(132767.0, dx));
            dy = std::max(-132768.0, std::min(132767.0, dy));
            object->objectID = 1;
             object->timeOfMeasurement = TimeOfMeasurement_oneMilliSecond;
            object->xDistance.value = (long)dx;
             object->xDistance.confidence = DistanceConfidence_unavailable;
            object->yDistance.value = (long)dy;
             object->yDistance.confidence = DistanceConfidence_unavailable;
             object->xSpeed.value = SpeedValueExtended_unavailable;
             object->xSpeed.confidence = SpeedConfidence_unavailable;
             object->ySpeed.value = SpeedValueExtended_unavailable;
             object->ySpeed.confidence = SpeedConfidence_unavailable;
            ASN_SEQUENCE_ADD(&mPerceivedObjectContainer, object);
        }
    }else{
    }
    // Set numberOfPerceivedObjects (mandatory r1 field)
    (*message).cpm.cpmParameters.numberOfPerceivedObjects = ((*message).cpm.cpmParameters.perceivedObjectContainer) ? (*message).cpm.cpmParameters.perceivedObjectContainer->list.count : 0;
    // --------------------------------------
    const auto sensors = lem.getSensors();
    // Create the SensorInformation Container
    // sensor range, Unit 0.1m
    // sensor open angle, Unit 0.1 degree 
    // --------------------------------------
    // std::cout << "sensors size::::" << sensors.size() << std::endl;
    uint sensorID = 1;
    if(false) for(const auto sensor:sensors){
        int OpeningAngleStart = 0; int OpeningAngleEnd = 3600; // FOV stub
        SensorInformation_t* SensorInformation = vanetza::asn1::allocate<SensorInformation_t>();
        SensorInformation->sensorID = sensorID;
        SensorInformation->type = SensorType_radar; // stub: treat all sensors as radar
        // Set mandatory DetectionArea as vehicleSensor CHOICE
        SensorInformation->detectionArea.present = DetectionArea_PR_vehicleSensor;
        SensorInformation->detectionArea.choice.vehicleSensor.refPointId = 0;
        SensorInformation->detectionArea.choice.vehicleSensor.xSensorOffset = 0;
        SensorInformation->detectionArea.choice.vehicleSensor.ySensorOffset = 0;
        // Add mandatory VehicleSensorProperty entry
        auto* prop = vanetza::asn1::allocate<VehicleSensorProperties_t>();
        prop->range = 2000;
        prop->horizontalOpeningAngleStart = 0;
        prop->horizontalOpeningAngleEnd = 3600;
        ASN_SEQUENCE_ADD(&SensorInformation->detectionArea.choice.vehicleSensor.vehicleSensorPropertyList, prop);

        if(!(*message).cpm.cpmParameters.sensorInformationContainer){
            (*message).cpm.cpmParameters.sensorInformationContainer = vanetza::asn1::allocate<SensorInformationContainer_t>();
        }
        ASN_SEQUENCE_ADD((*message).cpm.cpmParameters.sensorInformationContainer, SensorInformation);
        // Note: sensorInformationContainer is only set if sensors.size()>0
        sensorID++;
    }
    // --------------------------------------
    // Create the PerceptionRegion Container
    // --------------------------------------
    for(const auto sensor:sensors){
        int OpeningAngleStart = 0; int OpeningAngleEnd = 3600; // FOV stub
        long timeofmeasurement = referenceTime; // stub: assume measurement is current
        long deltaTimeOfMeasurement = referenceTime - timeofmeasurement;        // cout << "stationID::" << vdp.getStationId() << "; radialRange::" << radialRange << endl;
        
        if((OpeningAngleStart >= 0) && (OpeningAngleStart < 3600)){
        }else if(OpeningAngleStart == 3600){
        }else{
        }
        // cout << "stationID::" << vdp.getStationId() << "; OpeningAngleStart::" << OpeningAngleStart << endl;

        if((OpeningAngleEnd >= 0) && (OpeningAngleEnd < 3600)){
        }else if(OpeningAngleEnd == 3600){
        }else{
        }
        // cout << "stationID::" << vdp.getStationId() << "; OpeningAngleEnd::" << OpeningAngleEnd << endl;

    }
    //*************************************
    //     trigger attacks module
    //*************************************
    // Ensure POC exists for AddObj attack (attacker may have no env model objects)
    if((*message).cpm.cpmParameters.perceivedObjectContainer == nullptr && mF2MDFacility.getMbType() == mbTypes::LocalAttacker) {
        (*message).cpm.cpmParameters.perceivedObjectContainer = vanetza::asn1::allocate<PerceivedObjectContainer_t>();
    }
    mF2MDFacility.induceAttack((*message).cpm.cpmParameters.perceivedObjectContainer);
    // Update numberOfPerceivedObjects after potential attack modification
    (*message).cpm.cpmParameters.numberOfPerceivedObjects = ((*message).cpm.cpmParameters.perceivedObjectContainer) ? (*message).cpm.cpmParameters.perceivedObjectContainer->list.count : 0;
    // std::cout << "perceptionData value::" << cpm.cpmParameters.perceptionData <<std::endl;
    // if(cpm.cpmParameters.perceptionData != 0){
    //     FREEMEM(cpm.cpmParameters.perceptionData);
    //     cpm.cpmParameters.perceptionData = nullptr;
    // }


    EV_INFO << "CPM POC count: " << ((*message).cpm.cpmParameters.perceivedObjectContainer ? (*message).cpm.cpmParameters.perceivedObjectContainer->list.count : -1) << std::endl;
    // validate skipped here - done in sendCpm
    //std::cout << vdp.station_id()<<" packet transmission at "<< SIMTIME_STR(simTime())<<std::endl;

    return message;

}



/**
   *  @brief  stores the parameters defined in omnetpp.ini in the F2MD_CPMParameters.h file so that they can be used in the simulation.
*/
void F2MD_CPService::initParams(){

    /* Base Setting */
    CPparams.MixCpLocalAttacks = par("MixCpLocalAttacks");
    CPparams.RandomCpLocalMix = par("RandomCpLocalMix");

    CPparams.CP_LOCAL_ATTACKER_PROB = par("CP_LOCAL_ATTACKER_PROB"); // honor dedicated zero-attack configuration
    CPparams.CP_LOCAL_ATTACK_TYPE = static_cast<cpAttackTypes::Attacks>(par("CP_LOCAL_ATTACK_TYPE").intValue());

    CPparams.MaxRadarAngle = par("MaxRadarAngle");
    CPparams.MaxRadarRange = par("MaxRadarRange");

    CPparams.START_CPM_ATTACK = par("START_CPM_ATTACK");
    CPparams.MAX_CPM_DELTATIME = par("MAX_CPM_DELTATIME");
    CPparams.MAX_CPM_HISTORY_TIME = par("MAX_CPM_HISTORY_TIME");
    CPparams.KeepSameID = par("KeepSameID");


    /* Attack Parameters Setting */
    CPparams.cpParVar = par("cpParVar");
    CPparams.RandomDistOffsetX = par("RandomDistOffsetX");
    CPparams.RandomDistOffsetY = par("RandomDistOffsetY");
    CPparams.RandomSpeed = par("RandomSpeed");
    CPparams.RandomSpeedOffset = par("RandomSpeedOffset");
    CPparams.RandomAccel = par("RandomAccel");

    /* Detector Parameters Setting */
    CPparams.MaxMapBoundary = par("MaxMapBoundary");
    CPparams.MAX_PLAUSIBLE_ANGLE_CHANGE = par("MAX_PLAUSIBLE_ANGLE_CHANGE");
    CPparams.MAX_PLAUSIBLE_ACCEL = par("MAX_PLAUSIBLE_ACCEL");
    CPparams.MAX_PLAUSIBLE_DECEL = par("MAX_PLAUSIBLE_DECEL");
    CPparams.MAX_PLAUSIBLE_SPEED = par("MAX_PLAUSIBLE_SPEED");
    CPparams.TOLERANCE_EXCEED_SPEED = par("TOLERANCE_EXCEED_SPEED");
    CPparams.TOLERANCE_DEARTH_SPEED = par("TOLERANCE_DEARTH_SPEED");
    CPparams.SegmentAngle = par("SegmentAngle");

    /* Kalman Parameters Setting */
    CPparams.KALMAN_MIN_POS_RANGE = par("KALMAN_MIN_POS_RANGE");
    CPparams.KALMAN_MIN_SPEED_RANGE = par("KALMAN_MIN_SPEED_RANGE");
    CPparams.KALMAN_POS_RANGE = par("KALMAN_POS_RANGE");
    CPparams.KALMAN_SPEED_RANGE = par("KALMAN_SPEED_RANGE");
    CPparams.MAX_KALMAN_TIME = par("MAX_KALMAN_TIME");
    

    /* Pseudonym Parameters */
    CPparams.EnablePC = par("EnablePC");
    CPparams.Period_Change_Time = par("Period_Change_Time");
    CPparams.Tolerance_Buffer = par("Tolerance_Buffer");
    CPparams.Period_Change_Distance = par("Period_Change_Distance");
    CPparams.Random_Change_Chance = par("Random_Change_Chance");
    CPparams.PC_TYPE = pseudoChangeTypes::intPseudoChange[par("PC_TYPE").intValue()];

    /* Vehicular Characteristics*/
    CPparams.VEHICLE_LENGTH = par("VEHICLE_LENGTH");
    CPparams.VEHICLE_WIDTH = par("VEHICLE_WIDTH");
}

void F2MD_CPService::finish(){
  try {
    mF2MDFacility.finish();
    jwritecpmRX.addFinalTagToElement("CPM_RX",printFinalTagtoJson());
    jwritecpmRX.writeHeader();
    jwritecpmRX.addElement(jwritecpmRX.getJsonElementList("CPM_RX"));
    jwritecpmRX.writeFooter();
    if (outputjsonfilecpm.is_open()){
        outputjsonfilecpm << jwritecpmRX.getOutString()<<std::endl;
    }
    jwritelem.addFinalTagToElement("LP",printFinalTagtoJson());
    jwritelem.writeHeader();
    jwritelem.addElement(jwritelem.getJsonElementList("LP"));
    jwritelem.writeFooter();
    if (outputjsonfilelem.is_open()){
        outputjsonfilelem << jwritelem.getOutString() <<std::endl;
    }
    jwritecpmTX.addFinalTagToElement("CPM_TX",printFinalTagtoJson());
    jwritecpmTX.writeHeader();
    jwritecpmTX.addElement(jwritecpmTX.getJsonElementList("CPM_TX"));
    jwritecpmTX.writeFooter();
    if (outputjsonfilecpmEmit.is_open()){
        outputjsonfilecpmEmit << jwritecpmTX.getOutString()<<std::endl;
    }
    outputfilelog.close();
    outputjsonfilecpm.close();
    outputjsonfilelem.close();
    outputjsonfilecpmEmit.close();
    cSimpleModule::finish();
  } catch(const std::exception& e) {
    std::cerr << "finish exception: " << e.what() << std::endl;
  } catch(...) {
    std::cerr << "finish unknown exception" << std::endl;
  }
}


/**
 * @brief print the final tag To json file
 * 
 */
std::string F2MD_CPService::printFinalTagtoJson() {
    std::string tempStr ="";
    JsonWriter jw;
    jw.openJsonElement("final", true);
    return jw.getJsonElement("final");
}

/**
 * @brief print the receieved CPM information 
 * 
 */
std::string F2MD_CPService::printRXCpmtoJson(const vanetza::asn1::Cpm& msg, double checkfailed){

    std::string tempStr ="";

    JsonWriter jw;
   
    jw.openJsonElement("cpm", true);

    tempStr = jw.getSimpleTag("sourceId",std::to_string(msg->header.stationID),true);
    jw.addTagToElement("cpm", tempStr);

    long rfT;
    const auto rftime = (*msg).cpm.generationDeltaTime;
    rfT = (long)rftime; int res = 0;
    tempStr = jw.getSimpleTag("referenceTime",std::to_string(rfT),true);
    jw.addTagToElement("cpm", tempStr);

    tempStr = jw.getSimpleTag("rx_timestamp",SIMTIME_STR(simTime()),true);
    jw.addTagToElement("cpm", tempStr);
    tempStr = jw.getSimpleTag("checkfailed",std::to_string(checkfailed),true);
    jw.addFinalTagToElement("cpm", tempStr);
    
    return jw.getJsonElement("cpm");  
}


/**
 * @brief print the emitted CPM information 
 * 
 */
std::string F2MD_CPService::printTXCpmtoJson(const vanetza::asn1::Cpm& msg) {

    std::string tempStr ="";

    JsonWriter jw;
   
    jw.openJsonElement("cpm", true);

    tempStr = jw.getSimpleTag("sourcePseudoId",std::to_string(msg->header.stationID),true);
    jw.addTagToElement("cpm", tempStr);
    tempStr = jw.getSimpleTag("PseudonymChangeStrategy",pseudoChangeTypes::PseudoChangeNames[CPparams.PC_TYPE],false);
    jw.addTagToElement("cpm", tempStr); 
    tempStr = jw.getSimpleTag("sourceId",std::to_string(mVehicleDataProvider->getStationId()),true);
    jw.addTagToElement("cpm", tempStr);    
    tempStr = jw.getSimpleTag("sourceSumoId",mVehicleController->getVehicleId(),false);
    jw.addTagToElement("cpm", tempStr);
    
    auto mbtype = mF2MDFacility.getMbType();
    tempStr = jw.getSimpleTag("misbehaviorType",mbTypes::mbNames[mbtype],false);
    jw.addTagToElement("cpm", tempStr);   
    
    tempStr = jw.getSimpleTag("tx_timestamp",SIMTIME_STR(simTime()),true);
    jw.addTagToElement("cpm", tempStr);
    
    long rfT;
    const auto rftime = (*msg).cpm.generationDeltaTime;
    rfT = (long)rftime; int res = 0;
    tempStr = jw.getSimpleTag("referenceTime",std::to_string(rfT),true);
    jw.addTagToElement("cpm", tempStr);

    //getting vdp.position.x gives omnetpp format
    tempStr = jw.getSimpleTag("Xsumoposition", std::to_string(mVehicleDataProvider->longitude().value()),true);
    jw.addTagToElement("cpm", tempStr);
    tempStr = jw.getSimpleTag("Ysumoposition", std::to_string(mVehicleDataProvider->latitude().value()),true);
    jw.addTagToElement("cpm", tempStr);
    tempStr = jw.getSimpleTag("longitude", std::to_string((*msg).cpm.cpmParameters.managementContainer.referencePosition.longitude),true);
    jw.addTagToElement("cpm", tempStr);
    tempStr = jw.getSimpleTag("latitude", std::to_string((*msg).cpm.cpmParameters.managementContainer.referencePosition.latitude),true);
    jw.addTagToElement("cpm", tempStr);

    tempStr = jw.getSimpleTag("longspeed", std::to_string(mVehicleDataProvider->speed().value()),true);
    jw.addTagToElement("cpm", tempStr);

    tempStr = jw.getSimpleTag("longacceleration", std::to_string(mVehicleDataProvider->acceleration().value()),true);
    jw.addTagToElement("cpm", tempStr);

    int tempAV = std::round(mVehicleDataProvider->yaw_rate().value()*180/PI);
    tempStr = jw.getSimpleTag("zAngularVelocity", std::to_string(tempAV),true);
    jw.addTagToElement("cpm", tempStr);
    
    {
        PerceivedObjectContainer_t* POC = (*msg).cpm.cpmParameters.perceivedObjectContainer;
        if(POC != nullptr && POC->list.count > 0){
            jw.openJsonElementList("objects");
            for(int p = 0; p < POC->list.count; p++){
                jw.openJsonElement("object", true);
                tempStr = jw.getSimpleTag("objectId", std::to_string(POC->list.array[p]->objectID), true);
                jw.addTagToElement("object", tempStr);
                tempStr = jw.getSimpleTag("measurementDeltaTime", std::to_string(POC->list.array[p]->timeOfMeasurement), true);
                jw.addTagToElement("object", tempStr);
                tempStr = jw.getSimpleTag("position_xCoordinate", std::to_string(POC->list.array[p]->xDistance.value), true);
                jw.addTagToElement("object", tempStr);
                tempStr = jw.getSimpleTag("position_yCoordinate", std::to_string(POC->list.array[p]->yDistance.value), true);
                jw.addTagToElement("object", tempStr);
                tempStr = jw.getSimpleTag("velocityMagnitudeValue", std::to_string(POC->list.array[p]->xSpeed.value), true);
                jw.addTagToElement("object", tempStr);
                tempStr = jw.getSimpleTag("velocityDirection", std::to_string(POC->list.array[p]->ySpeed.value), true);
                if(p < POC->list.count - 1){
                    jw.addTagToElement("objects", jw.getJsonElement("object"));
                } else {
                    jw.addFinalTagToElement("objects", jw.getJsonElement("object"));
                }
            }
            jw.addFinalTagToElement("cpm", jw.getJsonElementList("objects"));
        }
    }
    return jw.getJsonElement("cpm");  
}


/**
 * @brief print the local perception LEM
 * 
 */
std::string F2MD_CPService::printperceivedlisttoJson(const std::string& title, const TrackedObjectsFilterRange& objs) {
    int i=0;
    int countLostTracingNum=0;
    
    std::string tempStr ="";
    std::string tempStrObj ="";
    JsonWriter jw;
   
    jw.openJsonElement("perceived list", true);

    tempStr = jw.getSimpleTag("timestamp",SIMTIME_STR(simTime()),true);
    jw.addTagToElement("perceived list", tempStr);

    //getting vdp.position.x gives omnetpp format
    traci::TraCIGeoPosition geoV;
    geoV.latitude = mVehicleDataProvider->latitude().value();
    geoV.longitude = mVehicleDataProvider->longitude().value();
    auto xyPos = mVehicleController->getTraCI().get()->convert2D(geoV);

    tempStr = jw.getSimpleTag("myStationId",std::to_string(mVehicleDataProvider->getStationId()),true);
    jw.addTagToElement("perceived list", tempStr);
    
    tempStr = jw.getSimpleTag("myPseudonym",std::to_string(myPseudonym),true);
    jw.addTagToElement("perceived list", tempStr);

    tempStr = jw.getSimpleTag("PseudonymChangeStrategy",pseudoChangeTypes::PseudoChangeNames[CPparams.PC_TYPE],false);
    jw.addTagToElement("perceived list", tempStr); 

    tempStr = jw.getSimpleTag("Xegosumoposition",std::to_string(mVehicleDataProvider->longitude().value()),true);
    jw.addTagToElement("perceived list", tempStr);
    
    tempStr = jw.getSimpleTag("Yegopsumoposition",std::to_string(mVehicleDataProvider->latitude().value()),true);
    jw.addTagToElement("perceived list", tempStr);

    tempStr = jw.getSimpleTag("longitude",std::to_string(mVehicleDataProvider->longitude().value()),true);
    jw.addTagToElement("perceived list", tempStr);
    
    tempStr = jw.getSimpleTag("latitude",std::to_string(mVehicleDataProvider->latitude().value()),true);
    jw.addTagToElement("perceived list", tempStr);


    tempStr = jw.getSimpleTag("longspeed",std::to_string(mVehicleDataProvider->speed().value()),true);
    jw.addTagToElement("perceived list", tempStr);

    tempStr = jw.getSimpleTag("longacceleration",std::to_string(mVehicleDataProvider->acceleration().value()),true);
    jw.addTagToElement("perceived list", tempStr);

    tempStr = jw.getSimpleTag("orientationangle",std::to_string(std::round(mVehicleDataProvider->heading().value() * 1800 / PI)),true);
    

    int sizeobjs = boost::size(objs);
    
    if (sizeobjs > 0){
        jw.addTagToElement("perceived list", tempStr);
        jw.openJsonElementList("objects");
        for (const auto& obj : objs){
            std::weak_ptr<EnvironmentModelObject> obj_ptr = obj.first;
            if (obj_ptr.expired()){
                countLostTracingNum++;
                continue; /*< objects remain in tracking briefly after leaving simulation */
            }
           
            auto envObj = obj_ptr.lock();

            jw.openJsonElement("object",true);

            tempStr = jw.getSimpleTag("objectId",envObj->getExternalId(),true);
            jw.addTagToElement("object", tempStr);

            tempStr = jw.getSimpleTag("xdistance",std::to_string(envObj->getCentrePoint().x.value() - mVehicleDataProvider->position().x.value()),true);
            jw.addTagToElement("object", tempStr);

            // Inverse the sign, position() use the OMNET reference system
            tempStr = jw.getSimpleTag("ydistance",std::to_string(mVehicleDataProvider->position().y.value() - envObj->getCentrePoint().y.value()),true);
            jw.addTagToElement("object", tempStr);
            
            //getting vdp.position.x gives omnetpp format
            traci::TraCIGeoPosition geoVobject;
            geoVobject.latitude = 0.0; // position not available via EnvironmentModelObject
            geoVobject.longitude = 0.0; // position not available via EnvironmentModelObject
            // convert2D removed

            tempStr = jw.getSimpleTag("Xobjectsumoposition",std::to_string(0.0),true);
            jw.addTagToElement("object", tempStr);     

            tempStr = jw.getSimpleTag("Yobjectsumoposition",std::to_string(0.0), true);
            jw.addTagToElement("object", tempStr);

            tempStr = jw.getSimpleTag("longitude",std::to_string(0.0 /* lon not on EnvironmentModelObject */),true);
            jw.addTagToElement("object", tempStr);

            tempStr = jw.getSimpleTag("latitude",std::to_string(0.0 /* lat not on EnvironmentModelObject */),true);
            jw.addTagToElement("object", tempStr);
            
            tempStr = jw.getSimpleTag("longspeed",std::to_string(0.0 /* speed not on EnvironmentModelObject */),true);
            jw.addTagToElement("object", tempStr);

            tempStr = jw.getSimpleTag("longacceleration",std::to_string(0.0 /* no acceleration on EnvironmentModelObject */),true);
            jw.addTagToElement("object", tempStr);

            int tempAngle = std::round(900 - 0.0 /* heading stub */ * 1800/PI);
            auto tempOrientationAngle = ((tempAngle % 3600) + 3600) % 3600;
            tempStr = jw.getSimpleTag("orientationangle",std::to_string(tempOrientationAngle),true);
            jw.addTagToElement("object", tempStr);
            
            auto tempYawRate = std::round(0.0 /* no yaw_rate on envObj */*180/PI);
            if(tempYawRate > 255){
                tempYawRate = 255;
            }else if(tempYawRate < -255){
                tempYawRate = -255;
            }
            tempStr = jw.getSimpleTag("zangularvelocity",std::to_string(tempYawRate),true);
            jw.addFinalTagToElement("object", tempStr);

            if (i < sizeobjs -1 -countLostTracingNum){ 
                jw.addTagToElement("objects", jw.getJsonElement("object"));
            }else if(i >= sizeobjs -1 -countLostTracingNum){
                jw.addFinalTagToElement("objects", jw.getJsonElement("object"));
            }
            i++;
        
        }
        jw.addTagToElement("perceived list",jw.getJsonElementList("objects"));
        tempStr = jw.getSimpleTag("NumPerceivedObj", std::to_string(sizeobjs - countLostTracingNum),true);
    }else{
        jw.addTagToElement("perceived list", tempStr);
        tempStr = jw.getSimpleTag("NumPerceivedObj", std::to_string(boost::size(objs)),true); 
    } 
    jw.addTagToElement("perceived list", tempStr);
    
    jw.openJsonElementList("Extend Perception List");
    auto mExtendPerceptionList = mExtendPerceptionTable.getExtendPerceptionList();
    for(auto it = mExtendPerceptionList.begin(); it != mExtendPerceptionList.end(); it++){
        jw.openJsonElement("ExtendPerceptionObj",true);
        
        tempStr = jw.getSimpleTag("LastUpdateTime",std::to_string((*it).LastUpdateTime),true);
        jw.addTagToElement("ExtendPerceptionObj", tempStr);

        tempStr = jw.getSimpleTag("PerceivedObjectID",std::to_string((*it).PerceivedObjectID),true);
        jw.addFinalTagToElement("ExtendPerceptionObj", tempStr);

        if(it == std::prev(mExtendPerceptionList.end())){
            jw.addFinalTagToElement("Extend Perception List",jw.getJsonElement("ExtendPerceptionObj"));
        }else{
            jw.addTagToElement("Extend Perception List",jw.getJsonElement("ExtendPerceptionObj"));
        }
    }

    jw.addFinalTagToElement("perceived list", jw.getJsonElementList("Extend Perception List"));
    return jw.getJsonElement("perceived list");  
} 


} // namespace artery
