
import carla
import time

client = carla.Client("127.0.0.1", 2000)
client.set_timeout(30)

world = client.get_world()

print("CARLA version:", client.get_server_version(), flush=True)
print("Map:", world.get_map().name, flush=True)

spawn_points = world.get_map().get_spawn_points()
print("Spawn points:", len(spawn_points), flush=True)

if not spawn_points:
    raise RuntimeError("Aucun point de spawn disponible")

# Choisir un véhicule disponible
blueprints = world.get_blueprint_library().filter("vehicle.*")
if not blueprints:
    raise RuntimeError("Aucun modèle de véhicule disponible")

vehicle = None

try:
    for point in spawn_points:
        vehicle = world.try_spawn_actor(blueprints[0], point)
        if vehicle is not None:
            break

    if vehicle is None:
        raise RuntimeError("Impossible de créer un véhicule")

    print("Vehicle created:", vehicle.id, flush=True)

    # Déplacement simple, sans Traffic Manager
    vehicle.set_autopilot(False)

    for i in range(15):
        vehicle.apply_control(
            carla.VehicleControl(
                throttle=0.3,
                steer=0.0
            )
        )

        location = vehicle.get_location()
        velocity = vehicle.get_velocity()
        speed = 3.6 * (
            velocity.x**2 +
            velocity.y**2 +
            velocity.z**2
        )**0.5

        print(
            f"Time: {i}s | "
            f"Position: ({location.x:.2f}, {location.y:.2f}) | "
            f"Speed: {speed:.1f} km/h",
            flush=True
        )

        time.sleep(1)

finally:
    if vehicle is not None:
        vehicle.destroy()
        print("Vehicle removed.", flush=True)

print("Simulation finished.", flush=True)
