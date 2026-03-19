import requests
import json

# Send Phase 2 sub-zones to Unity (Starts Phase 2 if Phase 1 is done)
url = "http://127.0.0.1:5000/start/"

data = {
    "phase2_zones": [
        {"minX": -52.0, "maxX": -36.5, "minZ": -24.1, "maxZ": 22.0}, # Drone 0 (Bottom-Left)
        {"minX": -34.7, "maxX": -19.4, "minZ": -24.1, "maxZ": 22.0}, # Drone 1 (Bottom-Right)
        {"minX": -52.0, "maxX": -36.5, "minZ": 24.0, "maxZ": 70.0},  # Drone 2 (Top-Left)
        {"minX": -34.7, "maxX": -19.4, "minZ": 24.0, "maxZ": 70.0}   # Drone 3 (Top-Right)
    ]
}

def send_phase2():
    try:
        print(f"Sending Phase 2 sub-zones to Unity at {url}...")
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print("Phase 2 received! If drones are waiting, they will start scouting now.")
        else:
            print(f"Failed! Status: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    send_phase2()
