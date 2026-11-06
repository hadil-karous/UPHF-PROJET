import os
import argparse,csv,json,math,pathlib,sys,time,threading,importlib.util,signal,struct
import carla,numpy as np,rclpy,yaml,traci
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from std_msgs.msg import ByteMultiArray,String
from sensor_msgs.msg import NavSatFix,Imu,Image,PointCloud2
from geometry_msgs.msg import TwistStamped
from etsi_its_cam_msgs.msg import CAM
from rosidl_runtime_py.convert import message_to_ordereddict
sys.path.insert(0,'/repo/cosimulation/sumo-integration/carla/Co-Simulation/Sumo')
from sumo_integration.carla_simulation import CarlaSimulation
from sumo_integration.sumo_simulation import SumoSimulation
from sumo_integration.bridge_helper import BridgeHelper
from run_synchronization import SimulationSynchronization
from carla_multi_agent.vehicle_agent import VehicleAgent
from carla_multi_agent.perception_contract import FrameAlignedWriter
out=pathlib.Path(os.environ.get('EXFMD_OUTPUT_DIR',str(pathlib.Path('/repo/results/integrated')/os.environ.get('EXFMD_RUN','demo-002')))); out.mkdir(parents=True,exist_ok=True)
(out/'running.json').write_text(json.dumps({'pid':__import__('os').getpid(),'started_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
rclpy.init(); executor=MultiThreadedExecutor(num_threads=5)
cam=load('cam_bridge','/ros_ws/artery_ros_bridge.py').ArteryRos2Bridge()
cpm=load('cpm_bridge','/ros_ws/cpm_os_bidge.py').CpmRos2Bridge()
class Recorder(Node):
    def __init__(self):
        super().__init__('exfmd_recorder'); self.counts={}; self.subs=[]; self.known=set(); self.lock=threading.Lock()
        self.perception_writer=FrameAlignedWriter('/dev/shm/perceived_0', self.archive_perception); self.log=(out/'ros-messages.jsonl').open('w')
        (out/'joined-perceptions').mkdir(exist_ok=True)
        for i in range(1,4):
            for kind in ['cam','cpm']: self.add(f'/simulator/vehicle{i}/{kind}',ByteMultiArray)
        self.add('/carla/hero/perceived_objects',String)
        self.add('/vehicle_1/gnss/fix',NavSatFix); self.add('/vehicle_1/imu/data',Imu); self.add('/vehicle_1/vehicle_status',TwistStamped)
        self.add('/vehicle_1/camera/image_raw',Image); self.add('/vehicle_1/lidar/points',PointCloud2)
        self.create_timer(0.3,self.discover)
    def discover(self):
        for topic,types in self.get_topic_names_and_types():
            if types==['etsi_its_cam_msgs/msg/CAM']: self.add(topic,CAM)
    def archive_perception(self, data):
        (out/'joined-perceptions'/('frame-'+str(data['frame_id'])+'.json')).write_text(json.dumps(data,allow_nan=False))
    def add(self,topic,typ):
        if topic in self.known:return
        self.known.add(topic)
        self.subs.append(self.create_subscription(typ,topic,lambda msg:self.record(topic,msg),10))
    def record(self,topic,msg):
        now=time.monotonic()
        with self.lock:
            x=self.counts.setdefault(topic,{'count':0,'first':now,'last':now}); x['count']+=1;x['last']=now
            if isinstance(msg,(Image,PointCloud2)): x['last_bytes']=len(msg.data); return
            d=message_to_ordereddict(msg)
            if isinstance(msg,ByteMultiArray): d={'bytes':len(msg.data),'hex':b''.join(msg.data).hex()}
            self.log.write(json.dumps({'wall_monotonic':now,'topic':topic,'message':d},default=lambda x:x.hex() if isinstance(x,bytes) else str(x))+'\n'); self.log.flush()
            if isinstance(msg,String):
                self.perception_writer.publish(json.loads(msg.data))
rec=Recorder()
for n in [cam,cpm,rec]:executor.add_node(n)
thread=threading.Thread(target=executor.spin,daemon=True); thread.start()
c=carla.Client('exfmd-carla',2000);c.set_timeout(60);w=c.get_world();original=w.get_settings()
rows=[];agent=None;sync=None;sumo=None;extras=[];report={'scenario':'explicit Gyrovia diagnostic derivative','rsu_count':1};start=time.monotonic()
def stop(signum,frame):raise KeyboardInterrupt('Stop requested')
signal.signal(signal.SIGTERM,stop)
try:
    if original.synchronous_mode:raise RuntimeError('Another tick owner active')
    sumo=SumoSimulation(str(out/'gyrovia.sumocfg'),0.05,'127.0.0.1',8813,False,2)
    cs=CarlaSimulation('exfmd-carla',2000,0.05);cs.client.set_timeout(60);sync=SimulationSynchronization(sumo,cs)
    cfg=yaml.safe_load(pathlib.Path('/repo/cosimulation/configs/gyrovia.yaml').read_text(encoding='utf-8-sig'))
    for i in range(75):
        sync.tick()
        frame_snapshot=w.get_snapshot()
        rec.perception_writer.register(frame_snapshot.frame,traci.simulation.getTime())
        with (out/'frame-times.jsonl').open('a') as timing:
            timing.write(json.dumps({'frame_id':frame_snapshot.frame,'carla_time_s':frame_snapshot.timestamp.elapsed_seconds,'sumo_time_s':traci.simulation.getTime()})+'\n')
        for sid,cid in sync.sumo2carla_ids.items():
            v=w.get_actor(cid)
            if agent is None and sid=='hero':
                v.attributes.get('role_name');agent=VehicleAgent(v,0,w,cfg);executor.add_node(agent)
                def save_rgb(image):
                    if not (out/'onboard.png').exists():image.save_to_disk(str(out/'onboard.png'))
                b=w.get_blueprint_library().find('sensor.camera.rgb');b.set_attribute('image_size_x','640');b.set_attribute('image_size_y','360');b.set_attribute('sensor_tick','0.5')
                camera=w.spawn_actor(b,carla.Transform(carla.Location(x=1.5,z=2.0)),attach_to=v);camera.listen(save_rgb);extras.append(camera)
                loc=v.get_location(); b2=w.get_blueprint_library().find('sensor.camera.rgb');b2.set_attribute('image_size_x','640');b2.set_attribute('image_size_y','360');b2.set_attribute('sensor_tick','0.5')
                overview=w.spawn_actor(b2,carla.Transform(carla.Location(x=loc.x,y=loc.y,z=25),carla.Rotation(pitch=-90)))
                overview.listen(lambda image:image.save_to_disk(str(out/'overview.png')) if not (out/'overview.png').exists() else None);extras.append(overview)
                b3=w.get_blueprint_library().find('sensor.lidar.ray_cast');b3.set_attribute('channels','16');b3.set_attribute('points_per_second','16000');b3.set_attribute('sensor_tick','0.5')
                lidar=w.spawn_actor(b3,carla.Transform(carla.Location(z=2.5)),attach_to=v)
                lidar.listen(lambda d:d.save_to_disk(str(out/'lidar.ply')) if not (out/'lidar.ply').exists() else None);extras.append(lidar)
            pos=v.get_location();sa=sumo.get_actor(sid);expected=BridgeHelper.get_carla_transform(sa.transform,sa.extent)
            speed=traci.vehicle.getSpeed(sid);heading=math.radians(v.get_transform().rotation.yaw)
            gps=w.get_map().transform_to_geolocation(pos)
            if sid=='hero' and agent:
                agent.update_state(v.get_transform(),carla.Vector3D(x=speed*math.cos(heading),y=speed*math.sin(heading)),v.get_angular_velocity(),v.get_control())
            idx={'hero':0,'hero1':1,'hero2':2}[sid]
            pathlib.Path('/dev/shm/agent_'+str(idx)).write_bytes(struct.pack('7d',gps.latitude,gps.longitude,(90+v.get_transform().rotation.yaw)%360,speed,0.,0.,w.get_snapshot().timestamp.elapsed_seconds))
            rows.append([i,w.get_snapshot().frame,traci.simulation.getTime(),sid,pos.x,pos.y,pos.z,speed,pos.distance(expected.location)])
        if i%10==0:print('step',i,'vehicles',len(sync.sumo2carla_ids),flush=True)
    time.sleep(1)
    report.update({'vehicles':len({r[3] for r in rows}),'samples':len(rows),'displacement_m':math.hypot([r for r in rows if r[3]=='hero'][-1][4]-[r for r in rows if r[3]=='hero'][0][4],[r for r in rows if r[3]=='hero'][-1][5]-[r for r in rows if r[3]=='hero'][0][5]),'max_sync_position_error_m':max(r[8] for r in rows),'max_speed_m_s':max(r[7] for r in rows),'fusion_objects':agent._semantic_det.detect(),'wall_seconds':time.monotonic()-start})
except BaseException as e:
    report['error']=repr(e);print('ERROR',repr(e),flush=True);raise
finally:
    report['ros_topics']=rec.get_topic_names_and_types();report['ros_nodes']=rec.get_node_names()
    if agent:
        if agent._semantic_det:agent._semantic_det.destroy()
        for sensor in agent._sensors:
            if sensor.is_alive: sensor.stop();sensor.destroy()
    for s in extras:
        try:s.stop();s.destroy()
        except Exception:pass
    if sync:sync.close()
    elif sumo:sumo.close()
    w.apply_settings(original);c.get_trafficmanager().set_synchronous_mode(False)
    executor.shutdown(timeout_sec=5)
    with rec.lock:report['topic_counts']=__import__('copy').deepcopy(rec.counts)
    with (out/'positions.csv').open('w',newline='') as f:
        wr=csv.writer(f);wr.writerow(['step','carla_frame','sumo_time','sumo_id','x','y','z','speed_m_s','sync_position_error_m']);wr.writerows(rows)
    (out/'report.json').write_text(json.dumps(report,indent=2));(out/'running.json').unlink(missing_ok=True)
    rclpy.shutdown();rec.log.close()
    print(json.dumps(report,indent=2),flush=True)
