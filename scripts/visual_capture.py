"""Optional RGB evidence capture. No changes to detection, tracking or F2MD."""
import json,pathlib,threading,time

class VisualCapture:
    def __init__(self,out):
        self.out=pathlib.Path(out);self.lock=threading.Lock();self.counts={};self.errors=[]
        (self.out/'video').mkdir(exist_ok=True)
    def camera(self,view,image,fov=75):
        try:
            folder=self.out/'video'/view;folder.mkdir(exist_ok=True)
            path=folder/('frame-%08d.png'%image.frame);temp=path.with_suffix('.tmp.png')
            image.save_to_disk(str(temp));temp.replace(path)
            record={'view':view,'frame_id':image.frame,'carla_time_s':image.timestamp,
                'width':image.width,'height':image.height,'fov':fov,
                'world_to_camera':image.transform.get_inverse_matrix(),
                'path':path.relative_to(self.out).as_posix(),'wall_time':time.time()}
            with self.lock:
                with (self.out/'camera-frames.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
                self.counts[view]=self.counts.get(view,0)+1
        except Exception as e:
            with self.lock:self.errors.append(repr(e))
    def state(self,frame,carla_time,sumo_time,actors):
        vehicles=[]
        for sid,actor,speed in actors:
            t=actor.get_transform();p=t.location;b=actor.bounding_box
            vehicles.append({'sumo_id':sid,'carla_id':actor.id,'x':p.x,'y':p.y,'z':p.z,'speed_m_s':speed,
                'bbox_world':[[v.x,v.y,v.z] for v in b.get_world_vertices(t)]})
        with (self.out/'visual-states.jsonl').open('a') as f:
            f.write(json.dumps({'frame_id':frame,'carla_time_s':carla_time,'sumo_time_s':sumo_time,'vehicles':vehicles})+'\n')
    def finish(self):
        (self.out/'visual-capture.json').write_text(json.dumps({'counts':self.counts,'errors':self.errors,
            'source':'sensor.camera.rgb CARLA; PNG saved by the CARLA API','synthetic_images':False},indent=2))
