import json
import os
from pathlib import Path
import carla

client=carla.Client('exfmd-carla',2000); client.set_timeout(10)
world=client.get_world()
result={'server_version':client.get_server_version(),'client_version':carla.__version__ if hasattr(carla,'__version__') else 'unknown',
    'map':world.get_map().name,'synchronous_mode':world.get_settings().synchronous_mode,
    'frame':world.get_snapshot().frame,'actors':len(world.get_actors())}
point=carla.Transform(carla.Location(x=1,y=2,z=3)).transform(carla.Location(x=4))
result['transform_return']=[point.x,point.y,point.z]
assert result['transform_return']==[5.,2.,3.]
assert not result['synchronous_mode'],'Another tick owner is active'
out=Path(os.environ['EXFMD_OUTPUT_DIR'])
(out/'preflight.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
