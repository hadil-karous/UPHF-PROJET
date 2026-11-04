
import carla
import threading

client = carla.Client("127.0.0.1", 2000)
client.set_timeout(30)
world = client.get_world()

print("Map:", world.get_map().name, flush=True)

settings = world.get_settings()
print("Synchronous mode:", settings.synchronous_mode, flush=True)
print("No rendering:", settings.no_rendering_mode, flush=True)

points = world.get_map().get_spawn_points()
if not points:
    raise RuntimeError("Aucun point de depart disponible")

point = points[0]

# Camera au-dessus de la route
camera_transform = carla.Transform(
    carla.Location(
        x=point.location.x,
        y=point.location.y,
        z=point.location.z + 15
    ),
    carla.Rotation(pitch=-80)
)

bp = world.get_blueprint_library().find(
    "sensor.camera.rgb"
)
bp.set_attribute("image_size_x", "640")
bp.set_attribute("image_size_y", "360")
bp.set_attribute("sensor_tick", "0.5")

camera = world.spawn_actor(bp, camera_transform)
captured = threading.Event()

def save_image(image):
    if not captured.is_set():
        try:
            image.save_to_disk("/tmp/gyrovia_demo.png")
            print("Image saved!", flush=True)
            captured.set()
        except Exception as e:
            print("Camera error:", e, flush=True)

try:
    camera.listen(save_image)
    print("Waiting for camera image...", flush=True)

    if settings.synchronous_mode:
        # Un seul client doit piloter les ticks.
        for _ in range(20):
            if captured.is_set():
                break
            world.tick()
            captured.wait(0.1)
    else:
        captured.wait(timeout=60)

    if not captured.is_set():
        print("No image received.", flush=True)
        print("Check rendering and simulation ticks.", flush=True)

finally:
    camera.stop()
    camera.destroy()

print("Finished.", flush=True)
