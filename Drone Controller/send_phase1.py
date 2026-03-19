import requests
import json

# Send only Phase 1 coordinates to Unity
url = "http://127.0.0.1:5000/start/"

data = {
    "corners": [
        {"x": -52.7, "y": 71.0},
        {"x": -18.4, "y": 70.3},
        {"x": -19.6, "y": -24.6},
        {"x": -53.0, "y": -25.1}
    ]
}

def send_phase1():
    try:
        print(f"Sending Phase 1 coordinates to Unity at {url}...")
        response = requests.post(url, json=data)
        if response.status_code == 200:
            print("Phase 1 initialized! Drones are moving to formation.")
        else:
            print(f"Failed! Status: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    send_phase1()
