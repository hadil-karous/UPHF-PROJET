/*******************************************************************************
 * @author  Jiahao Zhang
 * @email   jiahao.zhang96@gmail.com
 * @date    10/06/2021
 * @version 2.0
 *
 * TAM (Trusted Autonomous Mobility)
 * Copyright (c) 2013, 2021 Institut de Recherche Technologique SystemX
 * All rights reserved.
 *******************************************************************************/

#include "CpmChecks.h"
#include "R2ToLegacy.h"
#include "TemporalPlausibility.h"

template <typename T> int sgn(T val) {
    return (T(0) < val) - (val < T(0));
}


/**
   *  @brief create a new CPM checks configuration
*/
CpmChecks::CpmChecks(F2MD_CPParameters* params){
    this->params = params;
}


/**
   *  @brief  perform a series of tests on the given cpm.
   *  @param Cpm& cpm on which the tests must be performed
   *  @param NodeTableCpm* pointer to the historyTable
   *  @return 0 if genuine, 1 if an attack has been detected
*/
double CpmChecks::CpmChecksum(const vanetza::asn1::Cpm& msg, NodeTableCpm *detectedNodes, CpmCheckList& mCpmCheckList,
                            std::shared_ptr<const traci::API>* TraciLiteAPI){
    if (artery::cpm_a2::active_conversion) {
        auto& conversion=*artery::cpm_a2::active_conversion;
        if(auto* context=conversion.temporal_context) {
            if(!context->engine) throw std::runtime_error("A3 history engine missing");
            context->checks_called=true;
            auto& policy=context->policy;
            policy.maximum_age_ms=std::llround(params->MAX_CPM_DELTATIME*1000.);
            policy.maximum_interval_ms=policy.maximum_age_ms;
            policy.expiration_ms=std::llround(params->MAX_CPM_HISTORY_TIME*1000.);
            policy.acceleration_m_s2=params->MAX_PLAUSIBLE_ACCEL;
            policy.deceleration_m_s2=params->MAX_PLAUSIBLE_DECEL;
            policy.angular_rate_deg_s=params->MAX_PLAUSIBLE_ANGLE_CHANGE;
            policy.excess_speed_m_s=params->TOLERANCE_EXCEED_SPEED;
            conversion.control=context->engine->evaluate(context->message,context->receiver,context->receive_ms,policy,
                [&](double x,double y) { return speedPlausibility(x,y); });
            conversion.control["policy"]["speed_limit_m_s"]=params->MAX_PLAUSIBLE_SPEED;
            double speedFailures=0,speedConsistencyFailures=0,positionFailures=0;
            for(const auto& row:conversion.control["checks"]) if(row["status"]=="anomaly") {
                speedFailures+=row["check"]=="speed_plausibility";
                speedConsistencyFailures+=(row["check"]=="speed_consistency" || row["check"]=="direction_consistency");
                positionFailures+=row["check"]=="position_speed_consistency";
            }
            mCpmCheckList.setspeedPlausibility(speedFailures);
            mCpmCheckList.setspeedConsistency(speedConsistencyFailures);
            mCpmCheckList.setpositionSpeedConsistency(positionFailures);
            const double verdict=conversion.control["anomalies"].get<double>()>0?1.:0.;
            mCpmCheckList.setreport(verdict>0);
            return verdict;
        }
        const double verdict=artery::cpm_a2::evaluate(*artery::cpm_a2::active_conversion,
            [&](double x,double y) { return speedPlausibility(x,y); });
        mCpmCheckList.setspeedPlausibility(artery::cpm_a2::active_conversion->control["anomalies"].get<double>());
        mCpmCheckList.setreport(verdict>0);
        return verdict;
    }

    int res;
    double checkfailed = 0; 

    double distancePlausibilityResult = 0,speedPlausibilityResult = 0,
            speedConsistencyResult = 0,
            positionSpeedConsistencyResult = 0,
            kalmanPositionConsistencyResult = 0,
            kalmanSpeedConsistencyResult = 0,
            kalmanPositionSpeedConsistancyPositionResult = 0,
            kalmanPositionSpeedConsistancySpeedResult = 0;



    double TotaldistancePlausibilityResult = 0, TotalspeedPlausibilityResult = 0,
            TotalspeedConsistencyResult = 0,
            TotalpositionSpeedConsistencyResult = 0,
            TotalkalmanPositionConsistencyResult = 0,
            TotalkalmanSpeedConsistencyResult = 0,
            TotalkalmanPositionSpeedConsistancyPositionResult = 0,
            TotalkalmanPositionSpeedConsistancySpeedResult = 0;


    ReferencePosition_t oldEgoreferencePos,curEgoreferencePos;
    TraCIPosition curCartesianEgoPos,oldCartesianEgoPos;
    
    long senderId = msg->header.stationID;
    curEgoreferencePos = (*msg).cpm.cpmParameters.managementContainer.referencePosition;
    TraCIGeoPosition curEgoGeoPos, oldEgoGeoPos;
    curEgoGeoPos.longitude = curEgoreferencePos.longitude / 1e7;
    curEgoGeoPos.latitude = curEgoreferencePos.latitude / 1e7;
    curCartesianEgoPos = TraciLiteAPI->get()->convert2D(curEgoGeoPos);

        // r1: direct field access instead of container dispatch
    WGS84AngleValue_t orientationAngleValue = WGS84AngleValue_unavailable;
    SensorInformationContainer_t* sensors = (*msg).cpm.cpmParameters.sensorInformationContainer;
    if((*msg).cpm.cpmParameters.stationDataContainer != nullptr){
        auto& sdc = *(*msg).cpm.cpmParameters.stationDataContainer;
        if(sdc.present == StationDataContainer_PR_originatingVehicleContainer){
            auto* ovc = sdc.choice.originatingVehicleContainer.vehicleOrientationAngle;
            if(ovc) orientationAngleValue = ovc->value;
        }
    }

        // r1: direct POC access
    int dbg_poc = (*msg).cpm.cpmParameters.perceivedObjectContainer ? (*msg).cpm.cpmParameters.perceivedObjectContainer->list.count : -1;
    std::cerr << "CHECK: POC=" << dbg_poc << " sender=" << (*msg).header.stationID << std::endl;
    if((*msg).cpm.cpmParameters.perceivedObjectContainer != nullptr){
        PerceivedObjectContainer_t& addr_poc = *(*msg).cpm.cpmParameters.perceivedObjectContainer;
        for (int i = 0; i < addr_poc.list.count; i++){
            PerceivedObject_t *po = addr_poc.list.array[i];
                
                bool include = detectedNodes->includes(senderId);
                auto objectID = po->objectID; 

                // Get perceived vehicle dimension
                double Vlength = params->VEHICLE_LENGTH;
                double Vwidth = params->VEHICLE_WIDTH;
                
                // Plausibility checks
                SensorInformationContainer_t dummySIC = {};
                distancePlausibilityResult = distancePlausibility(po->xDistance.value, po->yDistance.value,
                                                0 /* r1: no zAngle */, Vlength, Vwidth, sensors ? *sensors : dummySIC);
                TotaldistancePlausibilityResult += distancePlausibilityResult;

                speedPlausibilityResult = speedPlausibility(po->xSpeed.value);
                TotalspeedPlausibilityResult += speedPlausibilityResult;

                if (include) {
                    NodeHistoryCpm* NodeHistory = detectedNodes->getNodeHistoryAddr(senderId);
                    vanetza::asn1::Cpm oldCpm = *(NodeHistory->getLatestCPMAddr());

                    oldEgoreferencePos = (*oldCpm).cpm.cpmParameters.managementContainer.referencePosition;
                    oldEgoGeoPos.latitude = oldEgoreferencePos.latitude / 1e7;
                    oldEgoGeoPos.longitude = oldEgoreferencePos.longitude / 1e7;
                    oldCartesianEgoPos =  TraciLiteAPI->get()->convert2D(oldEgoGeoPos);

                    PerceivedObject_t *oldCpmObj = findPoContainerAddr(objectID, oldCpm);
                    double oldCpmTime = NodeHistory->getLastUpdate();
                    long oldCPM_refTime; 
                    res = oldCPM_refTime = (*oldCpm).cpm.generationDeltaTime;
                    long curCPM_refTime;
                    res = curCPM_refTime = (*msg).cpm.generationDeltaTime;
                    long delta_Time = (curCPM_refTime - oldCPM_refTime)/1e3; // Unit 1s

                    if (oldCpmObj != nullptr && fabs(simTime().dbl() - oldCpmTime) < params->MAX_CPM_DELTATIME ){

                        // Consistancy checks
                        speedConsistencyResult = speedConsistency(po->xSpeed.value, 
                                                        po->ySpeed.value, 
                                                        oldCpmObj->xSpeed.value, 
                                                        oldCpmObj->ySpeed.value,
                                                        delta_Time);
                        TotalspeedConsistencyResult += speedConsistencyResult;


                        // re-calculate the perceived object position 
                        double curXobjpos = curCartesianEgoPos.x + po->xDistance.value / 100;
                        double curYobjpos = curCartesianEgoPos.y + po->yDistance.value / 100;
                        double oldXobjpos = oldCartesianEgoPos.x + oldCpmObj->xDistance.value / 100;
                        double oldYobjpos = oldCartesianEgoPos.y + oldCpmObj->yDistance.value / 100;
                        
                        positionSpeedConsistencyResult = positionSpeedConsistency(curXobjpos, curYobjpos,
                                                            po->xSpeed.value, 
                                                            oldXobjpos,oldYobjpos,
                                                            oldCpmObj->xSpeed.value, 
                                                            delta_Time);
                        
                        TotalpositionSpeedConsistencyResult += positionSpeedConsistencyResult;

                        
                        /* Consistency check with Kalman Filter */
                        // creat a new kalman filter for the perceived object and initialize
                        newKalmanFilter.senderID = senderId;
                        newKalmanFilter.PerceivedObjectID = objectID;
                        newKalmanFilter.mKalmanPC = Kalman_SI();
                        newKalmanFilter.mKalmanSC = Kalman_SI();
                        newKalmanFilter.mKalmanPSC = Kalman_SVI();
                        
                        Kalman_SI* kalmanPC;
                        Kalman_SI* kalmanSC;
                        Kalman_SVI* kalmanPSC;

                        // add this kalman filter in the globle kalman list
                        if(std::get<0>(FindKalmanFilter(senderId,objectID)) == false){
                            KalmanListTable.push_back(newKalmanFilter);
                            kalmanPC = &newKalmanFilter.mKalmanPC;
                            kalmanSC = &newKalmanFilter.mKalmanSC;
                            kalmanPSC = &newKalmanFilter.mKalmanPSC;
                        }else{
                            kalmanPC = &std::get<1>(FindKalmanFilter(senderId,objectID))->mKalmanPC;
                            kalmanSC = &std::get<1>(FindKalmanFilter(senderId,objectID))->mKalmanSC;
                            kalmanPSC = &std::get<1>(FindKalmanFilter(senderId,objectID))->mKalmanPSC;
                        }


                        /* Kalman Position Consistency Check */
                        kalmanPositionConsistencyResult = KalmanPositionConsistency(curXobjpos,curYobjpos,oldXobjpos,oldYobjpos,
                                                            po->xDistance.confidence, po->yDistance.confidence,
                                                            delta_Time, kalmanPC);

                        TotalkalmanPositionConsistencyResult += kalmanPositionConsistencyResult;



                        /* Kalman Speed Consistancy Check */
                        kalmanSpeedConsistencyResult = KalmanSpeedConsistancy(po->xSpeed.value,
                                                (po->xAcceleration ? po->xAcceleration->longitudinalAccelerationValue : 0),
                                                po->ySpeed.value, 
                                                po->xSpeed.confidence,
                                                oldCpmObj->ySpeed.value,
                                                delta_Time, kalmanSC);

                        TotalkalmanSpeedConsistencyResult += kalmanSpeedConsistencyResult;



                        /* Kalman Position Speed Consistency Check */
                        double retVal[2];

                        KalmanPositionSpeedConsistancy(curXobjpos, curYobjpos, 
                                                        po->xDistance.confidence, po->yDistance.confidence,
                                                        po->xSpeed.value,  
                                                        (po->xAcceleration ? po->xAcceleration->longitudinalAccelerationValue : 0),
                                                        po->xSpeed.confidence, 
                                                        po->ySpeed.value,
                                                        oldCpmObj->ySpeed.value,
                                                        delta_Time, kalmanPSC, retVal);

                        kalmanPositionSpeedConsistancyPositionResult = retVal[0];
                        kalmanPositionSpeedConsistancySpeedResult = retVal[1];

                        TotalkalmanPositionSpeedConsistancyPositionResult += kalmanPositionSpeedConsistancyPositionResult;
                        TotalkalmanPositionSpeedConsistancySpeedResult += kalmanPositionSpeedConsistancySpeedResult;
            
                    }
                }

                int tempResult = std::round(distancePlausibilityResult) + std::round(speedPlausibilityResult) + 
                                std::round(speedConsistencyResult) + std::round(positionSpeedConsistencyResult) +
                                std::round(kalmanPositionConsistencyResult) + std::round(kalmanSpeedConsistencyResult) +
                                std::round(kalmanPositionSpeedConsistancyPositionResult) + std::round(kalmanPositionSpeedConsistancySpeedResult);

                checkfailed += tempResult;
                if(tempResult > 0){
                    AttackedObject mAttackedObject;
                    mAttackedObject.ObjectID = objectID;
                    mAttackedObject.Checkfailed = ((int)distancePlausibilityResult) | ((int)speedPlausibilityResult << 1) |
                                        ((int)speedConsistencyResult << 2) | ((int)positionSpeedConsistencyResult << 3) |
                                        ((int)kalmanPositionConsistencyResult << 4) | ((int)kalmanSpeedConsistencyResult << 5) |
                                        ((int)kalmanPositionSpeedConsistancyPositionResult << 6) | ((int)kalmanPositionSpeedConsistancySpeedResult << 7);


                    mCpmCheckList.setAttackedObject(mAttackedObject);
                }
            }

            mCpmCheckList.setdistancePlausibility(std::round(TotaldistancePlausibilityResult));
            mCpmCheckList.setspeedConsistency(std::round(TotalspeedConsistencyResult));
            mCpmCheckList.setspeedPlausibility(std::round(TotalspeedPlausibilityResult));
            mCpmCheckList.setpositionSpeedConsistency(std::round(TotalpositionSpeedConsistencyResult));

            mCpmCheckList.setkalmanPositionConsistency(std::round(TotalkalmanPositionConsistencyResult));
            mCpmCheckList.setkalmanSpeedConsistency(std::round(TotalkalmanSpeedConsistencyResult));
            mCpmCheckList.setkalmanPositionSpeedConsistancyP(std::round(TotalkalmanPositionSpeedConsistancyPositionResult));
            mCpmCheckList.setkalmanPositionSpeedConsistancyS(std::round(TotalkalmanPositionSpeedConsistancySpeedResult));

        }
    if (checkfailed > 0){
        mCpmCheckList.setreport(1);
        return 1;
    }else{
        mCpmCheckList.setreport(0);
        return 0;
    }
}


/**
 * @brief find the perceived object container address 
 * 
 * @param objID 
 * @param lattestCpm 
 * @return PerceivedObject_t* 
 */
PerceivedObject_t* CpmChecks::findPoContainerAddr(int objID, vanetza::asn1::Cpm& lattestCpm){
    PerceivedObjectContainer_t* poc = (*lattestCpm).cpm.cpmParameters.perceivedObjectContainer;
    if(poc == nullptr) return nullptr;
    PerceivedObjectContainer_t* addr_objContainer = poc;
    for (int var = 0; var < addr_objContainer->list.count; var++){
        int objectId = addr_objContainer->list.array[var]->objectID;
        if(objectId == objID){
            return addr_objContainer->list.array[var];
        }
    }
    return nullptr;
}



/**
 * @brief In ENU(East-North-Up) reference system, check if the transmitted Euclidien 
 * distance to perceived object is outside of the transmitter's FoV threshold 
 * 
 * @param xDistance X coordinate distance, Unit: 0.01m
 * @param yDistance Y coordinate distance, Unit: 0.01m
 * @param heading perceived object orientation angle, Unit: 0.1 degrees
 * @param length perceived vehicle length, Unit: 1m
 * @param width perceived vehicle width, Unit: 1m
 * @param vehicle_referencePosition Ego reference position 
 * @param sensors implemented sensors' information
 * @return double, check result, detector activated returns 1
 */
double CpmChecks::distancePlausibility(double xDistance, double yDistance, double heading, double length, double width, SensorInformationContainer_t& sensors) {
    
    double distance = mdmLib.calculateDistanceXY(xDistance, yDistance);
    double MaxRadarRange = params->MaxRadarRange;
    double sensor_range;
    double openAngleStart, openAngleEnd;
    vector<artery::geometry::Polygon> List_sensorFoV;   
    bool CheckResult = 0;

    //-------------------------------- calculate the polygon of the FoV --------------------------------
    typedef artery::geometry::Point RefPoint_t;
    for(int sensorIndix=0; sensorIndix < sensors.list.count ; sensorIndix++){

        artery::geometry::Polygon sensorFoV;
        // Ego reference position (0,0)
        bg::append(sensorFoV.outer(), RefPoint_t(0,0));

        long sensorType = sensors.list.array[sensorIndix]->sensorID; // r1: sensorID only
        // choose the case of sensor type
        switch (sensorType){
            case SensorType_radar:
        sensor_range = 150.0; // r1: no perceptionRegionShape, stub
        openAngleStart = 0; // r1 stub
        openAngleEnd = 3600; // r1 stub
        }

        // define the method to draw lineOfSight
        // for each nlineOfSight degree, we draw a line
        int deltaAngle = (int(openAngleEnd - openAngleStart + params->Tolenrance_angle*2*10) % 3600 + 3600) % 3600;
        int numLine = deltaAngle / params->SegmentAngle;

        if((deltaAngle % params->SegmentAngle) == 0){
            numLine += 1;
        }else{
            numLine += 2;
        }


        // add each point of FoV in the polygon
        for(int i=0; i < numLine; i++){
            double temp1,temp2;
            if(i < numLine-1){
                temp1 = std::sin((openAngleStart+i*params->SegmentAngle)*PI/1800) * sensor_range / 10;
                temp2 = std::cos((openAngleStart+i*params->SegmentAngle)*PI/1800) * sensor_range / 10;
                bg::append(sensorFoV.outer(), RefPoint_t(temp1,temp2));
            }else{
                temp1 = std::sin(openAngleEnd*PI/1800) * sensor_range / 10;
                temp2 = std::cos(openAngleEnd*PI/1800) * sensor_range / 10;
                bg::append(sensorFoV.outer(), RefPoint_t(temp1,temp2));
            }
            // cout << "FoV :::" << temp1 << ";" << temp2 << endl;
        }
        bg::append(sensorFoV.outer(), RefPoint_t(0,0));
        //-------------------------------------------------------------------------------------------------- 

        List_sensorFoV.push_back(sensorFoV);
    }



    // if (distance > (MaxRadarRange + length)* 100){
    //     CheckResult = 1;
    // }

    // re-calculate 4 corners of the perceived object
    Eigen::MatrixXd RotationMatrix(3,3);
    RotationMatrix <<  cos(heading/1800 * PI),  -sin(heading/1800 * PI), xDistance/100,
                       sin(heading/1800 * PI),   cos(heading/1800 * PI), yDistance/100,
                                     0,                0,             1;

    Eigen::Vector3d CornUR, CornUL, CornBR, CornBL;

    // Rotation start from x-axis 
    // corner 1: upper right corner
    CornUR <<       0,  width/2,  1;
    // corner 2: upper left corner
    CornUL << -length,  width/2,  1;
    // corner 3: bottom right corner
    CornBR <<       0, -width/2,  1;
    // corner 4: bottom left corner
    CornBL << -length, -width/2,  1;

    auto res1 = RotationMatrix * CornUR;
    auto res2 = RotationMatrix * CornUL;
    auto res3 = RotationMatrix * CornBR;
    auto res4 = RotationMatrix * CornBL;

    // cout << res1 << endl;
    // cout << res2 << endl;
    // cout << res3 << endl;
    // cout << res4 << endl;
    
    RefPoint_t PointUR(res1(0),res1(1));
    RefPoint_t PointUL(res2(0),res2(1));
    RefPoint_t PointBR(res3(0),res3(1));
    RefPoint_t PointBL(res4(0),res4(1));

    
    for(auto const& sensorfov : List_sensorFoV){
        // !IsPointInPolygon means that the point is in the sensor's FoV
        // if the point is not in all sensors' FoV, CheckResult returns 1
        // otherwise, CheckResult returns 0
        
        // check if any one corner is in the sensor's FoV
        bool tempRes = (IsPointInPolygon(PointUR, sensorfov) || IsPointInPolygon(PointUL, sensorfov) ||
                         IsPointInPolygon(PointBR, sensorfov) || IsPointInPolygon(PointBL, sensorfov));

        // cout << "point UR::" << IsPointInPolygon(PointUR, sensorfov) << ";" 
        //      << "point UL::" << IsPointInPolygon(PointUL, sensorfov) << ";"
        //      << "point BR::" << IsPointInPolygon(PointBR, sensorfov) << ";"
        //      << "point BL::" << IsPointInPolygon(PointBL, sensorfov) << ";" 
        //      << "tempRes::" << tempRes << endl;
        
        CheckResult = CheckResult || tempRes;
    }
    

    // cout << "CheckResult:::" << !CheckResult << endl;
    // std::cout << "********distance plausibility : "<< CheckResult << endl;
    return !CheckResult;
}


/**
 * @brief Check if the transmitted speed value of the perceived object is higher than
 * a certain threshold, present in a cartesian coordinate system
 * 
 * @param xSpeed, the x component of the velocity vector
 * @param ySpeed, the y component of the velocity vector
 * @return double, check result, detector activated returns 1
 */
double CpmChecks::speedPlausibility(double xSpeed, double ySpeed){    
    double speed = mdmLib.calculateSpeedXY(xSpeed, ySpeed);
    if (speed > params->MAX_PLAUSIBLE_SPEED*100) {
        return 1;
    }
    else {
        return 0;
    }
}

/**
 * @brief Check if the transmitted speed value of the perceived object is higher than
 * a certain threshold, present in a polar coordinate system
 * 
 * @param Speed, magnitude of the velocity vector on the reference plane
 * @return double, check result, detector activated returns 1
 */
double CpmChecks::speedPlausibility(double Speed){   
    if (Speed > params->MAX_PLAUSIBLE_SPEED*100) {
        return 1;
    }
    else {
        return 0;
    }
}


/**
 * @brief Check if the transmitted speed value in two successive CPM is consistent 
 * 
 * @param curSpeed current velocity magnitude, Unit 0.01 m/s
 * @param curSpeedDirection current velocity direction, Unit 0.1 degree
 * @param oldSpeed precedent velocity magnitude, Unit 0.01 m/s
 * @param oldSpeedDirection precedent velocity direction, Unit 0.1 degree
 * @param time time difference between two successive CPM, Unit 1s
 * @return double, check result, detector activated returns 1
 */
double CpmChecks::speedConsistency(double curSpeed, double curSpeedDirection, double oldSpeed, double oldSpeedDirection, double time) { 
    
    // check if the velocity magnitude change is plausible
    double speedDelta = curSpeed - oldSpeed;
    if(speedDelta >= 0){
        // MAX_PLAUSIBLE_ACCEL, unit 1 m/s**2
        if(fabs(speedDelta) > fabs(params->MAX_PLAUSIBLE_ACCEL) * time * 1e2){
            return 1;
        }
    }else{
        if(fabs(speedDelta) > fabs(params->MAX_PLAUSIBLE_DECEL) * time * 1e2){
            return 1;
        }
    }

    // check if the velocity direction change is plausible
    int angleDelta = curSpeedDirection - oldSpeedDirection;
    if(angleDelta >= 1800){
        angleDelta = ((-angleDelta) % 3600 + 3600) % 3600;
    }else if((angleDelta < 0) && (angleDelta >= -1800)){
        angleDelta = -angleDelta;
    }else{
        angleDelta = ((angleDelta) % 3600 + 3600) % 3600;
    }

    // MAX_PLAUSIBLE_ANGLE_CHANGE, unit 1 degree
    if(angleDelta > params->MAX_PLAUSIBLE_ANGLE_CHANGE * time * 10){
        return 1;
    }

    return 0;
}


/**
 * @brief check if the transmitted position in two successive CPM is consistent with the speed of the same perceived object
 * 
 * @param curXDistance current X position, Unit 1 m
 * @param curYDistance current Y position, Unit 1 m
 * @param curSpeed current speed of the perceived object, Unit 0.01m/s
 * @param oldXDistance precedent X position, Unit 1 m
 * @param oldYDistance precedent Y position, Unit 1 m
 * @param oldSpeed precedent speed of the perceived object, Unit 0.01m/s
 * @param time time difference between two successive CPM, Unit 1s
 * @return double, check result, detector activated returns 1 
 */
double CpmChecks::positionSpeedConsistency(double curXDistance, double curYDistance, double curSpeed,
                                double oldXDistance, double oldYDistance, double oldSpeed, double time){

    double delta_distance = mdmLib.calculateDistanceXY(oldXDistance-curXDistance,oldYDistance-curYDistance);
    double maxSpeed = std::max(curSpeed, oldSpeed) + params->TOLERANCE_EXCEED_SPEED * 100;
    // double minSpeed = std::min(curSpeed, oldSpeed) - params->TOLERANCE_DEARTH_SPEED * 100;

    // cout << " delta_distance :: " << delta_distance << endl; 
    // cout << "cur x position :: " << curXDistance << endl;
    // cout << "old x position :: " << oldXDistance << endl;
    // cout << "cur y position :: " << curYDistance << endl;
    // cout << "old y position :: " << oldYDistance << endl;
    // cout << " time ::" << time << endl;
    // cout << " maxSpeed ::" << maxSpeed << endl;
    // cout << " minSpeed ::" << minSpeed << endl;
    // cout << " maxDistance change ::" << time * maxSpeed * 0.001 << endl;
    // cout << " minDistance change ::" << time * minSpeed * 0.001 << endl;

    // if ((delta_distance > time * maxSpeed) || (delta_distance < time * minSpeed)){
    if(delta_distance > time * maxSpeed){
        return 1;
    }
    return 0;
}



/**
 * @brief check if the transmitted position in two successive CPM is consistent, Simple linear Kalman filter
 * 
 * @param curXPosition perceived object X current position, Unit 1m
 * @param curYPosition perceived object Y current position, Unit 1m
 * @param oldXPosition perceived object X precedent position, Unit 1m
 * @param oldYPosition perceived object Y precedent position, Unit 1m
 * @param curXPostionConfidence Unit 0.01m
 * @param curYPostionConfidence Unit 0.01m
 * @param time time difference between two successive CPM, Unit 1s
 * @return double, check result, detector activated returns 1
 */
double CpmChecks::KalmanPositionConsistency(double curXPosition, double curYPosition, double oldXPosition, double oldYPosition,
                                            double curXPostionConfidence, double curYPostionConfidence, double time, Kalman_SI* kalmanSI){  
    
    // cout << "---------kalman position consistency init :: " << kalmanSI->isInit() << endl;  
    
    if(kalmanSI->isInit() == false){
        kalmanSI->setInitial(curXPosition, curYPosition);
        return 0;
    }else{
        if(time < params->MAX_KALMAN_TIME){
            float Delta[2];

            double curPosConfX = curXPostionConfidence;
            if ((curPosConfX < params->KALMAN_MIN_POS_RANGE * 100) || (curPosConfX == DistanceConfidence_unavailable)) {
                curPosConfX = params->KALMAN_MIN_POS_RANGE;
            }else{
                curPosConfX /= 100;
            }

            double curPosConfY = curYPostionConfidence;
            if ((curPosConfY < params->KALMAN_MIN_POS_RANGE * 100) || (curPosConfY ==DistanceConfidence_unavailable)) {
                curPosConfY = params->KALMAN_MIN_POS_RANGE;
            }else{
                curPosConfY /= 100;
            }


            kalmanSI->getDeltaPos(time, curXPosition, curYPosition,
                curPosConfX, curPosConfY, Delta);

            double curPosConf = sqrt(pow(curPosConfX, 2.0) + pow(curPosConfY, 2.0));

            double ret_1 = 1 - sqrt(pow(Delta[0], 2.0) + pow(Delta[1], 2.0)) / (4 * params->KALMAN_POS_RANGE * curPosConf * time);
            
            // cout << "---------KALMAN_POS_RANGE :: " << params->KALMAN_POS_RANGE  << endl;
            // cout << "---------curPosConf :: " << curPosConf  << endl;
            // cout << "---------part 1 :: " << sqrt(pow(Delta[0], 2.0) + pow(Delta[1], 2.0))  << endl;
            // cout << "---------part 2 :: " << (4 * params->KALMAN_POS_RANGE * curPosConf * time) << endl;
            // cout << "---------ret_1 :: " << ret_1 << endl;

            if (isnan(ret_1)) {
                ret_1 = 1;
            }
            if (ret_1 < 0.5) {
                ret_1 = 1;
            }else{
                ret_1 = 0;
            }
            return ret_1;
        }else{
            kalmanSI->setInitial(curXPosition, curYPosition);
            return 0;
        }
    }
}



/**
 * @brief Check the change of the transmitted disntance to the perceived object is
 * inconsistent with the speed of the same perceived object, the simple linear kalman filter can be used here
 * @param curSpeed Unit 0.01 m/s
 * @param curAccel Unit 0.1 m/s^2
 * @param curSpeedDirection Unit 0.1 degree
 * @param curSpeedConfidence Unit 0.01 m/s
 * @param time Unit 1s
 * @param kalmanSI 
 * @return double 
 */
double CpmChecks::KalmanSpeedConsistancy(double curSpeed, double curAccel, double curSpeedDirection, double curSpeedConfidence,
                                        double oldSpeedDirection, double time, Kalman_SI* kalmanSI){
                                        
    double curSpdConfX, curSpdConfY;
    double curSpdX, curSpdY, curAccX, curAccY;

    curSpdX = (curSpeed/100) * sin(curSpeedDirection * PI / 1800);
    curSpdY = (curSpeed/100) * cos(curSpeedDirection * PI / 1800);
    if(curAccel >= 160){
        curAccel = 0;
    }
    curAccX = (curAccel/10) * sin(curSpeedDirection * PI / 1800);
    curAccY = (curAccel/10) * cos(curSpeedDirection * PI / 1800);

    // cout << "---------kalman position consistency init :: " << kalmanSI->isInit() << endl;
    auto rotation_angle_1 = ((int)(curSpeedDirection - oldSpeedDirection)% 3600 + 3600) % 3600;
    auto rotation_angle_2 = ((int)(oldSpeedDirection - curSpeedDirection)% 3600 + 3600) % 3600;

    if (kalmanSI->isInit() == false) {
        kalmanSI->setInitial(curSpdX, curSpdY);
        return 0;
    }
    else if(std::min(rotation_angle_1,rotation_angle_2) > 600){
        kalmanSI->setInitial(curSpdX, curSpdY);
        return 0;
    }
    else {
        if (time < params->MAX_KALMAN_TIME) {
            float Delta[2];

            if(curSpeedConfidence != SpeedConfidence_unavailable  && curSpeedConfidence > params->KALMAN_MIN_SPEED_RANGE){
                curSpdConfX = (curSpeedConfidence/100) * sin(curSpeedDirection * PI / 1800);
                curSpdConfY = (curSpeedConfidence/100) * cos(curSpeedDirection * PI / 1800);
            }else{
                // curSpdConfX = params->KALMAN_MIN_SPEED_RANGE * sin(curSpeedDirection * PI / 1800);
                // curSpdConfY = params->KALMAN_MIN_SPEED_RANGE * cos(curSpeedDirection * PI / 1800); 
                curSpdConfX = params->KALMAN_MIN_SPEED_RANGE;
                curSpdConfY = params->KALMAN_MIN_SPEED_RANGE; 
            }

            kalmanSI->getDeltaPos(time, curSpdX, curSpdY, curAccX,
                curAccY, curSpdConfX, curSpdConfY, Delta);

            double curSpdConf = sqrt(pow(curSpdConfX, 2.0) + pow(curSpdConfY, 2.0));

            double ret_1 = 1 - sqrt(pow(Delta[0], 2.0) + pow(Delta[1], 2.0)) / (params->KALMAN_SPEED_RANGE * curSpdConf * time);

            // cout << "---------KALMAN_SPEED_RANGE :: " << params->KALMAN_SPEED_RANGE  << endl;
            // cout << "---------curPosConf :: " << curSpdConf  << endl;
            // cout << "---------part 1 :: " << sqrt(pow(Delta[0], 2.0) + pow(Delta[1], 2.0))  << endl;
            // cout << "---------part 2 :: " << (params->KALMAN_SPEED_RANGE * curSpdConf * time) << endl;
            // cout << "---------ret_1 :: " << ret_1 << endl;


            if (isnan(ret_1)) {
                ret_1 = 1;
            }
            if (ret_1 < 0.5) {
                ret_1 = 1;
            }else{
                ret_1 = 0;
            }

            return ret_1;
        }
        else {
            kalmanSI->setInitial(curSpdX, curSpdY);
            return 0;
        }
    }
}




/**
 * @brief linear kalman filter, check if position and speed are consistent between two successive CPMs.
 * 
 * @param curXPosition Unit 0.01m
 * @param curYPosition Unit 0.01m
 * @param curXPositionConfidence Unit 0.01m
 * @param curYPositionConfidence Unit 0.01m
 * @param curSpeed Unit 0.01m/s
 * @param curAccel Unit 0.1m/s-2
 * @param curSpeedConfidence Unit 0.01m
 * @param curSpeedDirection Unit 0.1 degree
 * @param time Unit 1s
 * @param kalmanSVI 
 * @param retVal 
 */
void CpmChecks::KalmanPositionSpeedConsistancy(double curXPosition, double curYPosition, double curXPositionConfidence, double curYPositionConfidence, 
                                                double curSpeed, double curAccel, double curSpeedConfidence, double curSpeedDirection, double oldSpeedDirection, 
                                                double time, Kalman_SVI* kalmanSVI, double retVal[]){
    
    double curSpdConfX, curSpdConfY;                                                    
    if(curAccel >= 160){
        curAccel = 0;
    }
    double Ax = (curAccel/10) * sin(curSpeedDirection * PI / 1800);
    double Ay = (curAccel/10) * cos(curSpeedDirection * PI / 1800);
    double curSpeedX = (curSpeed/100) * sin(curSpeedDirection * PI / 1800);
    double curSpeedY = (curSpeed/100) * cos(curSpeedDirection * PI / 1800);

    auto rotation_angle_1 = ((int)(curSpeedDirection - oldSpeedDirection)% 3600 + 3600) % 3600;
    auto rotation_angle_2 = ((int)(oldSpeedDirection - curSpeedDirection)% 3600 + 3600) % 3600;
    

    if (!kalmanSVI->isInit()) {
        retVal[0] = 0;
        retVal[1] = 0;
        kalmanSVI->setInitial(curXPosition, curYPosition, curSpeedX, curSpeedY);
    }
    else if(std::min(rotation_angle_1,rotation_angle_2) > 600){
        retVal[0] = 0;
        retVal[1] = 0;
        kalmanSVI->setInitial(curXPosition, curYPosition, curSpeedX, curSpeedY);   
    }
    else {
        if (time < params->MAX_KALMAN_TIME) {
            float Delta[4];

           
            if ((curXPositionConfidence < params->KALMAN_MIN_POS_RANGE * 100) || (curXPositionConfidence == DistanceConfidence_unavailable)) {
                curXPositionConfidence = params->KALMAN_MIN_POS_RANGE;
            }

            if ((curYPositionConfidence < params->KALMAN_MIN_POS_RANGE * 100) || (curYPositionConfidence == DistanceConfidence_unavailable)) {
                curYPositionConfidence = params->KALMAN_MIN_POS_RANGE;
            }


            if(curSpeedConfidence != SpeedConfidence_unavailable && curSpeedConfidence > params->KALMAN_MIN_SPEED_RANGE){
                curSpdConfX = (curSpeedConfidence/100) * sin(curSpeedDirection * PI / 1800);
                curSpdConfY = (curSpeedConfidence/100) * cos(curSpeedDirection * PI / 1800);      
            }else{
                // curSpdConfX = params->KALMAN_MIN_SPEED_RANGE * sin(curSpeedDirection * PI / 1800);
                // curSpdConfY = params->KALMAN_MIN_SPEED_RANGE * cos(curSpeedDirection * PI / 1800);
                curSpdConfX = params->KALMAN_MIN_SPEED_RANGE;
                curSpdConfY = params->KALMAN_MIN_SPEED_RANGE;                
            }

            kalmanSVI->getDeltaPos(time, curXPosition, curYPosition,
                curSpeedX, curSpeedY, Ax, Ay, curXPositionConfidence, curYPositionConfidence,
                curSpdConfX, curSpdConfY, Delta);

            double curPosConf = sqrt(pow(curXPositionConfidence, 2.0) + pow(curYPositionConfidence, 2.0));
            double ret_1 = 1 - sqrt(pow(Delta[0], 2.0) + pow(Delta[2], 2.0)) / (4 * params->KALMAN_POS_RANGE * curPosConf * time);
            // cout << "---------ret_1 :: " << ret_1 << endl;
            if (isnan(ret_1)) {
                ret_1 = 1;
            }

            if (ret_1 < 0.5) {
                ret_1 = 1;
            }
            else {
                ret_1 = 0;
            }

            double curSpdConf = sqrt(pow(curSpdConfX, 2.0) + pow(curSpdConfY, 2.0));
            double ret_2 = 1 - sqrt(pow(Delta[1], 2.0) + pow(Delta[3], 2.0)) / (params->KALMAN_SPEED_RANGE * curSpdConf * time);
            // cout << "---------ret_2 :: " << ret_2 << endl;
            if (isnan(ret_2)) {
                ret_2 = 1;
            }

            if (ret_2 < 0.5) {
                ret_2 = 1;
            }
            else {
                ret_2 = 0;
            }
            retVal[0] = ret_1;
            retVal[1] = ret_2;
        }
        else {
            retVal[0] = 0;
            retVal[1] = 0;
            kalmanSVI->setInitial(curXPosition, curYPosition, curSpeedX, curSpeedY);
        }
    }
}




/**
 * @brief test if the defined point is in the predefined polygon
 * 
 * @param pt point under test
 * @param polygon polygon in test
 * @return true, In the polygon
 * @return false, Not in the polygon
 */
bool CpmChecks::IsPointInPolygon(artery::geometry::Point pt, artery::geometry::Polygon polygon){
    // Count polygon size
    return bg::within(pt,polygon);
}



/**
 * @brief find the same kalman filter with the same senderID and objectID
 * 
 * @param senderID 
 * @param objectID 
 * @return tuple<bool,KalmanFilterList*> 
 */
tuple<bool, KalmanFilterList*> CpmChecks::FindKalmanFilter(uint32_t senderID, uint32_t objectID){
    for(auto& i:KalmanListTable){
        uint32_t a[2]={senderID, objectID};
        if(i == a){
                KalmanFilterList* AddrKFL= &i;
                return make_tuple(true, AddrKFL);
        }
    }
    return make_tuple(false, nullptr);
}
