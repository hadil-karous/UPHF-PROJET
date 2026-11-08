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

#include "F2MD_CPFacility.h"
#include "R2ToLegacy.h"
#include "TemporalPlausibility.h"

using namespace omnetpp;
using namespace vanetza;
using namespace traci;

/**
   *  @brief  Creates a CPM Processing Facility module, with the given parameters
*/
F2MD_CPFacility::F2MD_CPFacility(const artery::VehicleDataProvider* VehProvider, const traci::VehicleController* VehController, F2MD_CPParameters& CPparams, unsigned long* PseudonymID){
    mVehicleDataProvider = VehProvider;
    mVehicleController = VehController;
    params = &CPparams;
    myPseudonym = PseudonymID;

}

/**
   *  @brief  Initialize the CPM Processing Facility module, with the given parameters
*/
void F2MD_CPFacility::initialize()
{
    params = params;
    const std::string id = mVehicleController->getVehicleId();
    auto& vehicle_api = mVehicleController->getTraCI()->vehicle;

    // ------ Initialize F2MD  ------
    params->MAX_PLAUSIBLE_SPEED = vehicle_api.getMaxSpeed(id) + 0.1;
    // A3 checks remote R2 estimates using the explicitly configured policy.
    // Receiver capabilities must not silently replace that configuration.
    // Keep the original A2 speed initialization and the non-A3 behaviour.
    if (!std::getenv("EXFMD_A3_TEMPORAL")) {
        params->MAX_PLAUSIBLE_ACCEL = vehicle_api.getAccel(id) + 0.1;
        params->MAX_PLAUSIBLE_DECEL = vehicle_api.getDecel(id) + 0.1;
    }
    
    // ------ Initialize detectors ----
    mCpmChecks = CpmChecks(params);

    // Initialize globle parameters
    LastCPLocalAttackIndex = -1;
    memset(accusedNodesCP,0,sizeof(accusedNodesCP));
    accusedNodesLengthCP = 0;


    // Depending on the Attacking Probability, the node will be an attacker or a genuine
    myMdType = induceMisbehavior(params->CP_LOCAL_ATTACKER_PROB);
    std::cerr << "Node mbType=" << mbTypes::mbNames[myMdType] << " prob=" << params->CP_LOCAL_ATTACKER_PROB << std::endl;
    

    // ------ Initialize Attack  ------
    switch (myMdType) {
        // Genuine vehicle: green color
        case mbTypes::Genuine: {
            vehicle_api.setColor(id, libsumo::TraCIColor(0, 255, 0, 255));
            myAttackType = cpAttackTypes::Genuine;
        } break;

        case mbTypes::LocalAttacker: {
            if (params->MixCpLocalAttacks) {
                int AtLiSize = sizeof(params->MixCpLocalAttacksList) / sizeof(params->MixCpLocalAttacksList[0]);
                int localAttackIndex = 0;
                // each attacker executes a random attack
                if (params->RandomCpLocalMix) {
                    localAttackIndex = genLib.RandomInt(0, AtLiSize - 1);
                }
                else {
                    // mix all implemented attacks in order.
                    if (LastCPLocalAttackIndex < (AtLiSize - 1)) {
                        localAttackIndex = LastCPLocalAttackIndex + 1;
                        LastCPLocalAttackIndex = localAttackIndex;
                    }else {
                        localAttackIndex = 0;
                        LastCPLocalAttackIndex = 0;
                    }
                }
                myAttackType = params->MixCpLocalAttacksList[localAttackIndex];
            }
            else {
                myAttackType = params->CP_LOCAL_ATTACK_TYPE;
            }
            // Initialise attack
            mdAttack = MDCpmAttack();
            mdAttack.init(params, mVehicleController);

            // (Attacker) vehicle: red color
            vehicle_api.setColor(id, libsumo::TraCIColor(255, 0, 0, 255));
        } break;
        
        default:
            vehicle_api.setColor(id, libsumo::TraCIColor(0, 0, 0, 255));
            break;
    }

    detectedNodes = NodeTableCpm();


    int myId = mVehicleDataProvider->getStationId();
    string str_id = to_string(myId);



    // For Json
    string suffix = ".json";
    
    //if (myMdType == mbTypes::Genuine)
   //{ 
        //string outjsonfilecpmReport_name = "output/ATTACK/CPM/Report/logjson_cpm_report";
        string outjsonfilecpmReport_name = "output/ATTACK/CPM/Report/";
        outjsonfilecpmReport_name.append(cpAttackTypes::AttackNames[params->CP_LOCAL_ATTACK_TYPE]);
        if(params->KeepSameID == true){
            outjsonfilecpmReport_name.append("_KeepSameID");
        }
         //mkdir savePath
        struct stat info;
        if ((stat(outjsonfilecpmReport_name.c_str(), &info) != 0) || !(info.st_mode & S_IFDIR)) {
            mkdir(outjsonfilecpmReport_name.c_str(), 0777);
        }
 
        outjsonfilecpmReport_name.append ("/logjson_cpm_report_");

        outjsonfilecpmReport_name.append(str_id);
        //outjsonfilecpmReport_name.append (to_string(params->CP_LOCAL_ATTACK_TYPE));
        outjsonfilecpmReport_name.append (suffix);
        outputjsonfilecpmReport.open(outjsonfilecpmReport_name,ios::out);
        jwritecpmReport.openJsonElementList("CPM_REPORT");
   //} 
}


/**
   *  @brief depending on node's attacking type (genuine or attacker), an attack is performed on the cpm before being sent
   *  @param PerceivedObjectContainer_t* cpm payload data
*/
void F2MD_CPFacility::induceAttack(PerceivedObjectContainer_t* poc){
    if (myMdType == mbTypes::LocalAttacker && simTime().dbl() > params->START_CPM_ATTACK){
        mdAttack.launchAttack(myAttackType, poc);
    }else {
        if (myMdType == mbTypes::Genuine) {
            // EV_INFO << "Genuine, nothing is done" << endl;
        }
        else {
            // EV_INFO << "AttackType : " << myAttackType << " with poc->list.count perceived objects, nothing done." << endl;
        }
    }
}





/**
   *  @brief defines the attack type of the node (genuine or attacker)
   *  @param double number of attacker already in the sim
*/
static double totalCPGenuine = 0;
static double totalCPLocalAttacker = 0;
mbTypes::Mbs F2MD_CPFacility::induceMisbehavior(double LocalAttackerRatio)
{   
    // corrected, because the first node is always Genuinem, cant adapt our scenario
    double realFactor = totalCPLocalAttacker / (totalCPGenuine + totalCPLocalAttacker);
    if (LocalAttackerRatio > realFactor) {
        totalCPLocalAttacker++;
        return mbTypes::LocalAttacker;
    }
    else {
        totalCPGenuine++;
        return mbTypes::Genuine;
    }
}

/**
   *  @brief perform all the checks on the cpm received to detect a potential attack
   *  @param vanetza::asn1::Cpm& cpm received
*/
double F2MD_CPFacility::onCPM(const vanetza::asn1::Cpm& msg, const::vanetza::MacAddress& neighborMAcId,
                                         CpmCheckList& mCpmCheckList, std::map<int,int>& PseudoID2ArteryID){  
    if (auto* conversion=artery::cpm_a2::active_conversion) {
        if (auto* temporal=conversion->temporal_context) {
            temporal->facility_called=true;
            // A3 owns object history with full time and IDs. Do not poison the
            // old NodeHistoryCpm/accused-node tables with partial or rejected data.
            return mCpmChecks.CpmChecksum(msg,nullptr,mCpmCheckList,nullptr);
        }
    }
    
    // add local perception list
    vanetza::asn1::Cpm lastCpm;
    treatAttackFlags();

    // run checkst
    auto vehicle_api = mVehicleController->getTraCI();
    double checkfailed = mCpmChecks.CpmChecksum(msg, &detectedNodes, mCpmCheckList, &vehicle_api);

// ------------------------------------------------------------------------------------------------------

    int senderID = msg->header.stationID;

    // add the cpm received to the HistoryNodeTable
    if (!detectedNodes.includes(senderID)) {
        NodeHistoryCpm newNode(senderID);
        newNode.addCPM(msg);
        detectedNodes.put(senderID, newNode, params->MAX_CPM_HISTORY_TIME);
    }
    else {
        NodeHistoryCpm* existingNode = detectedNodes.getNodeHistoryAddr(
            senderID);

        lastCpm = *(existingNode->getLatestCPMAddr());
        existingNode->addCPM(msg);
    }

// ----------------------------------------------------------------------------------------------------
    if (checkfailed > 0) {
        try { addAccusedNode(senderID); } catch(...) { std::cerr << "addAccusedNode crash" << std::endl; }
    }
    

// begin write the report copied from CAM

// Generate reports for the Misbehavior Authority
    if (false && checkfailed && (myMdType == mbTypes::Genuine)) { // writeReport disabled - crashes on empty lastCpm
        // std::cout << "********check report ******"<< std::endl;
        try { jwritecpmReport.addTagToElement("CPM_REPORT", writeReport(msg, neighborMAcId, mCpmCheckList, lastCpm, PseudoID2ArteryID)); } catch(const std::exception& e) { std::cerr << "writeReport ex: " << e.what() << std::endl; } catch(...) { std::cerr << "writeReport unknown ex" << std::endl; }

       

        //makedecision (idsuspect, attacktype, location )

        //MDReport reportBase;
        //reportBase.setGenerationTime(simTime().dbl());
        //reportBase.setSenderPseudo(myPseudonym);
        //reportBase.setReportedPseudo(senderPseudo);

        //reportBase.setSenderRealId(myId);
        //reportBase.setReportedRealId(senderID);

        /*reportBase.setMbType(mbTypes::mbNames[BSMrecvd->getSenderMbType()]);
        reportBase.setAttackType(attackTypes::AttackNames[BSMrecvd->getSenderAttackType()]);
        reportBase.setSenderGps(Coord(curGPSCoordinates.x, curGPSCoordinates.y));
        reportBase.setReportedGps(BSMrecvd->getSenderGpsCoordinates());

        char nameV1[32] = "mdaV1";
        mdStats.getReport(nameV1, reportBase);
        if (params->writeReportsV1 && myBsmNum > 0) {
            writeReport(reportBase, version, mdv, bsmCheckV1, BSMrecvd);
        }

        if (params->writeListReportsV1 && myBsmNum > 0) {
            writeListReport(reportBase, version, mdv, bsmCheckV1, BSMrecvd);
        }

        if (params->sendReportsV1 && myBsmNum > 0) {
            sendReport(reportBase, version, mdv, bsmCheckV1, BSMrecvd);
        }*/
    }


//end write report

    return checkfailed;
}



/**
   *  @brief turn the color of a node into black if detected
*/
void F2MD_CPFacility::treatAttackFlags(){
    // int myID = mVehicleDataProvider->getStationId();
    auto myID = (*myPseudonym);
    // cout << "isAccusedNode(myID) " << myID << " :: " << isAccusedNode(myID) << endl;
    if (isAccusedNode(myID)){
        auto& vehicle_api = mVehicleController->getTraCI()->vehicle;
        const std::string id = mVehicleController->getVehicleId();
        vehicle_api.setColor(id, libsumo::TraCIColor(255, 255, 255, 255));
    }
}

/**
   *  @brief adds the given ID to the list of detected nodes
*/
void F2MD_CPFacility::addAccusedNode(unsigned int id)
{
    bool found = false;
    for (int var = 0; var < accusedNodesLengthCP; ++var) {
        if (accusedNodesCP[var] == id) {
            found = true;
        }
    }

    if (!found) {
        accusedNodesCP[accusedNodesLengthCP] = id;
        accusedNodesLengthCP++;
    }
}


/**
   *  @result returns True is the node is already accused, False if not
*/
bool F2MD_CPFacility::isAccusedNode(unsigned int id)
{
    for (int var = 0; var < accusedNodesLengthCP; ++var) {
        if (accusedNodesCP[var] == id) {
            return true;
        }
    }
    return false;
}
/**
 * @brief print the final tag To json file
 * 
 */
std::string F2MD_CPFacility::printFinalTagtoJson() {
    std::string tempStr ="";
    JsonWriter jw;
    jw.openJsonElement("final", true);
    return jw.getJsonElement("final");
}


std::string F2MD_CPFacility::writeV2XPDU(const vanetza::asn1::Cpm& msg, const::vanetza::MacAddress& neighborMAcId, std::map<int,int>& PseudoID2ArteryID)
{
    string macid="";

    for (int i =0; i<neighborMAcId.octets.size();i++)
    {
        macid.append(std::to_string(neighborMAcId.octets[i]));
    } 

    JsonWriter jw;
    std::string tempStr ="";

    jw.openJsonElement("oneV2XPdu", true);

    tempStr = jw.getSimpleTag("sourcePseudoId", std::to_string(msg->header.stationID),true);
    jw.addTagToElement("oneV2XPdu", tempStr);

    if(params->EnablePC == true){
        tempStr = jw.getSimpleTag("sourceRealId", std::to_string(PseudoID2ArteryID.find(msg->header.stationID)->second), true);
        jw.addTagToElement("oneV2XPdu", tempStr);
    }else{
        tempStr = jw.getSimpleTag("sourceRealId", std::to_string(msg->header.stationID),true);
        jw.addTagToElement("oneV2XPdu", tempStr);
    }
    

    tempStr = jw.getSimpleTag("sourceMacId", macid,true);
    jw.addTagToElement("oneV2XPdu", tempStr);

    long rfT;
    const auto rftime = (*msg).cpm.generationDeltaTime;
    rfT = (long)rftime; int res = 0;
    tempStr = jw.getSimpleTag("referenceTime",std::to_string(rfT),true);
    jw.addTagToElement("oneV2XPdu", tempStr);

    tempStr = jw.getSimpleTag("longitude", std::to_string((*msg).cpm.cpmParameters.managementContainer.referencePosition.longitude),true);
    jw.addTagToElement("oneV2XPdu", tempStr);
    
    tempStr = jw.getSimpleTag("latitude", std::to_string((*msg).cpm.cpmParameters.managementContainer.referencePosition.latitude),true);
    jw.addTagToElement("oneV2XPdu", tempStr);
    //std::cout << mVehicleDataProvider->getStationId() <<"   ******** 1 ******" << 1 << std::endl;
    
    for(int i=0; i< 1 ; i++){
       if(true){
                jw.addTagToElement("PerceivedObjectContainer", tempStr);
                jw.openJsonElementList("objects");
                //cout << ":::::::::::" << POC->list.count << endl;
                PerceivedObjectContainer_t* POC = (*msg).cpm.cpmParameters.perceivedObjectContainer;
                if(POC == nullptr) { return jw.getJsonElement("oneV2XPdu"); }
                for(int p = 0; p < POC->list.count; p++){
                    jw.openJsonElement("object",true);
                    tempStr = jw.getSimpleTag("objectId", std::to_string((long)POC->list.array[p]->objectID), true);
                    jw.addTagToElement("object", tempStr);
                    tempStr = jw.getSimpleTag("measurementDeltaTime", std::to_string(POC->list.array[p]->timeOfMeasurement),true);
                    jw.addTagToElement("object", tempStr);
                    tempStr = jw.getSimpleTag("position_xCoordinate", std::to_string(POC->list.array[p]->xDistance.value),true);
                    jw.addTagToElement("object", tempStr);
                    tempStr = jw.getSimpleTag("position_yCoordinate", std::to_string(POC->list.array[p]->yDistance.value),true);
                    jw.addTagToElement("object", tempStr);
                    tempStr = jw.getSimpleTag("velocityMagnitudeValue", std::to_string(POC->list.array[p]->xSpeed.value),true);
                    jw.addTagToElement("object", tempStr);
                    tempStr = jw.getSimpleTag("velocityDirection", std::to_string(POC->list.array[p]->ySpeed.value),true);
                    jw.addTagToElement("object", tempStr);
                    if (p < POC->list.count -1){ 
                        jw.addTagToElement("objects", jw.getJsonElement("object"));
                    }else{
                        jw.addFinalTagToElement("objects", jw.getJsonElement("object"));
                    } 
                }
                
                jw.addFinalTagToElement("PerceivedObjectContainer",jw.getJsonElementList("objects"));
            }else{
                jw.addFinalTagToElement("PerceivedObjectContainer", tempStr);
            }
            jw.addFinalTagToElement("oneV2XPdu",jw.getJsonElement("PerceivedObjectContainer"));  
       }

    

    return jw.getJsonElement("oneV2XPdu");   

}


/**
   *  @brief write a new report
*/
std::string F2MD_CPFacility::writeReport(const vanetza::asn1::Cpm& msg, const::vanetza::MacAddress& neighborMAcId,
             CpmCheckList& mCpmCheckList, vanetza::asn1::Cpm& lastCpm, std::map<int,int>& PseudoID2ArteryID)
{
        //BasicCheckReport bcr = BasicCheckReport(reportBase);
        //bcr.setReportedCheck(bsmCheck);
        //bcr.writeStrToFile("../../testreport.json", params->serialNumber, "1",bcr.getReportPrintableJson(), NULL);

    //NodeHistoryCpm* NodeHistory = detectedNodes.getNodeHistoryAddr(msg->header.stationID);
    //vanetza::asn1::Cpm lastCpm = *(NodeHistory->getLatestCPMAddr());

    bool consistencycheckon = false;
    std::string tempStr ="";

    JsonWriter jw;
   
    jw.openJsonElement("report", true);

    tempStr = jw.getSimpleTag("generationTime",SIMTIME_STR(simTime()),true);
    jw.addTagToElement("report", tempStr);

    tempStr = jw.getSimpleTag("reporterPseudoId", std::to_string((*myPseudonym)),true);
    jw.addTagToElement("report", tempStr);

    tempStr = jw.getSimpleTag("reporterArteryId", std::to_string((mVehicleDataProvider->getStationId())),true);
    jw.addTagToElement("report", tempStr);

    tempStr = jw.getSimpleTag("version","1",true);
    jw.addTagToElement("report", tempStr);
    
    jw.openJsonElement("observationlocation", false);

    tempStr = jw.getSimpleTag("x", std::to_string(mVehicleDataProvider->position().x.value()),true);
    jw.addTagToElement("observationlocation", tempStr);

    tempStr = jw.getSimpleTag("y", std::to_string(mVehicleDataProvider->position().y.value()),true);
    jw.addFinalTagToElement("observationlocation", tempStr);


    jw.addTagToElement("report",jw.getJsonElement("observationlocation"));

    jw.openJsonElement("content",false);       

    jw.openJsonElementList("observationSet");
    for (int i=0; i< mCpmCheckList.getAttackedObject().size(); i++){
        jw.openJsonElement("observationByTarget", true);

        tempStr = jw.getSimpleTag("targetId", std::to_string(mCpmCheckList.getAttackedObject()[i].ObjectID),true);
        jw.addTagToElement("observationByTarget", tempStr);

        tempStr = jw.getSimpleTag("attackType", cpAttackTypes::AttackNames[params->CP_LOCAL_ATTACK_TYPE],false);
        jw.addTagToElement("observationByTarget", tempStr);

        tempStr = jw.getSimpleTag("check", std::to_string(mCpmCheckList.getAttackedObject()[i].Checkfailed),true);
        jw.addFinalTagToElement("observationByTarget", tempStr);

        if (mCpmCheckList.getAttackedObject()[i].Checkfailed > 3)
            consistencycheckon = true ; 

        if (i==mCpmCheckList.getAttackedObject().size()-1){
            jw.addFinalTagToElement("observationSet",jw.getJsonElement("observationByTarget"));

        }
        else{
            jw.addTagToElement("observationSet",jw.getJsonElement("observationByTarget"));

        } 
    } 

    jw.addTagToElement("content",jw.getJsonElementList("observationSet"));

    jw.openJsonElementList("V2XPduEvidence");
    
    
    //write current received CPM as evidence
    //std::cout << "****On est CURRENT CPM******" << std::endl;

    if (consistencycheckon)
    {
        jw.addTagToElement("V2XPduEvidence",writeV2XPDU(msg, neighborMAcId, PseudoID2ArteryID));
        jw.addFinalTagToElement("V2XPduEvidence",writeV2XPDU(lastCpm, neighborMAcId, PseudoID2ArteryID));
    } 
    else 
    {
        jw.addFinalTagToElement("V2XPduEvidence",writeV2XPDU(msg,neighborMAcId, PseudoID2ArteryID));
    } 
        
    //
    //std::cout << "****On est LAST CPM******" << std::endl;

    //write last received CPM as evidence 
   


    jw.addFinalTagToElement("content",jw.getJsonElementList("V2XPduEvidence"));  

    jw.addFinalTagToElement("report",jw.getJsonElement("content"));     
    return jw.getJsonElement("report");    
}

void F2MD_CPFacility::finish()
{
    jwritecpmReport.addFinalTagToElement("CPM_REPORT",printFinalTagtoJson());
    jwritecpmReport.writeHeader();
    jwritecpmReport.addElement(jwritecpmReport.getJsonElementList("CPM_REPORT"));  
    jwritecpmReport.writeFooter();
    if (outputjsonfilecpmReport.is_open()){
       
        outputjsonfilecpmReport << jwritecpmReport.getOutString()<<std::endl; 
    } 
    outputjsonfilecpmReport.close();
  

    //cSimpleModule::finish();
} 
