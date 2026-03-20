"""
ResQNet — Full Flow Simulation Test
Tests the entire pipeline: Scout → Search → Rescue
Requires all module servers to be running:
  python scout.py      # port 8001
  python search.py     # port 8002
  python rescue.py     # port 8003
"""

import httpx
import asyncio
import json
import sys

SCOUT  = "http://localhost:8001"
SEARCH = "http://localhost:8002"
RESCUE = "http://localhost:8003"

TIMEOUT = 120.0

def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def sub(title):
    print(f"\n--- {title} ---")

async def run():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:

        # PHASE 1: SCOUT
        header("PHASE 1: SCOUT")

        # F2: Split zones first
        sub("F2: Split Zones (4x4 grid)")
        r = await c.post(f"{SCOUT}/api/scout/split_zones", json={"grid_size": 4})
        zones = r.json()
        print(f"[+] Total zones: {zones['total_zones']}")
        print(f"[+] Bounds: {json.dumps(zones['bounds'], indent=2)}")
        nonempty = [z for z in zones["zones"] if z["frame_count"] > 0]
        print(f"[+] Zones with frames: {len(nonempty)}")
        for z in nonempty[:3]:
            print(f"    {z['zone_id']}: {z['frame_count']} frames")

        # F1: Detect on a sample frame
        sub("F1: Detect Frame (Drone 1, Frame 50)")
        r = await c.post(f"{SCOUT}/api/scout/detect", json={"drone_id": 1, "frame_num": 50})
        det = r.json()
        print(f"[+] GPS: {det.get('gps')}")
        print(f"[+] VLM Description: {det['vlm_description'][:200]}...")
        print(f"[+] Detections keys: {list(det['detections'].keys())}")

        # F3: Danger rating for a zone with frames
        if nonempty:
            target_zone = nonempty[0]["zone_id"]
            sub(f"F3: Danger Rating ({target_zone})")
            r = await c.post(f"{SCOUT}/api/scout/danger_rating", json={"zone_id": target_zone})
            dr = r.json()
            print(f"[+] Danger: {dr['danger_rating']}")
            print(f"[+] Hazards: {dr['hazards']}")
            print(f"[+] Reasoning: {dr['reasoning'][:200]}...")

            # F4: Density
            sub(f"F4: People Density ({target_zone})")
            r = await c.post(f"{SCOUT}/api/scout/density", json={"zone_id": target_zone})
            dn = r.json()
            print(f"[+] Estimated people: {dn['estimated_people']}")
            print(f"[+] Density level: {dn['density_level']}")

            # F5: Priority
            sub(f"F5: Rescue Priority ({target_zone})")
            r = await c.post(f"{SCOUT}/api/scout/priority", json={"zone_id": target_zone})
            pr = r.json()
            print(f"[+] Priority: {pr['priority']}/10")
            print(f"[+] Reasoning: {pr['reasoning'][:200]}...")

        # F6: Strategy
        sub("F6: Rescue Strategy")
        r = await c.post(f"{SCOUT}/api/scout/strategy", json={})
        st = r.json()
        print(f"[+] Strategy: {st['strategy'][:200]}...")
        print(f"[+] Phases: {len(st.get('phases', []))}")

        # F7: Escape routes
        sub("F7: Escape Routes")
        r = await c.post(f"{SCOUT}/api/scout/escape_routes")
        er = r.json()
        print(f"[+] Safety zones: {len(er.get('safety_zones', []))}")
        print(f"[+] Escape routes: {len(er.get('escape_routes', []))}")

        # PHASE 2: SEARCH
        header("PHASE 2: SEARCH")

        # F1: Continuous update
        sub("F1: Continuous Update (Drone 1, 3 frames)")
        r = await c.post(f"{SEARCH}/api/search/update", json={"drone_id": 1, "start_frame": 100, "num_frames": 3})
        up = r.json()
        print(f"[+] Frames processed: {up['frames_processed']}")
        for d in up["detections_summary"]:
            print(f"    Frame {d.get('frame_num', '?')}: urgency={d.get('urgency', '?')}, people={d.get('people_visible', '?')}")

        # F2: Medical detection
        sub("F2: Medical Emergency Detection (Drone 2, Frame 100)")
        r = await c.post(f"{SEARCH}/api/search/medical", json={"drone_id": 2, "frame_num": 100})
        med = r.json()
        print(f"[+] Emergency detected: {med['emergency_detected']}")
        print(f"[+] Severity: {med['severity']}")
        print(f"[+] Alarm: {med['alarm']}")

        # F3: Threat detection
        sub("F3: Threat Detection (Drone 3, Frame 200)")
        r = await c.post(f"{SEARCH}/api/search/threats", json={"drone_id": 3, "frame_num": 200})
        thr = r.json()
        print(f"[+] Threat detected: {thr['threat_detected']}")
        print(f"[+] Threat level: {thr['threat_level']}")
        print(f"[+] Alarm: {thr['alarm']}")

        # Check alarms
        sub("Active Alarms")
        r = await c.get(f"{SEARCH}/api/search/alarms")
        al = r.json()
        print(f"[+] Total alarms: {al['total']}")
        for a in al["alarms"]:
            print(f"    🚨 {a['type']} — Drone {a['drone_id']} Frame {a['frame_num']}")

        # PHASE 3: RESCUE
        header("PHASE 3: RESCUE")

        # F1: Safety instructions
        sub("F1: Safety Instructions (Drone 1, Frame 150)")
        r = await c.post(f"{RESCUE}/api/rescue/safety_instructions", json={"drone_id": 1, "frame_num": 150})
        si = r.json()
        print(f"[+] Scene: {si['scene_description'][:200]}...")
        print(f"[+] Persons identified: {len(si['persons_identified'])}")
        for inst in si["safety_instructions"][:3]:
            print(f"    → [{inst.get('priority','?')}] {inst.get('instruction','')[:100]}")
        print(f"[+] Guidelines: {si['general_guidelines'][:200]}")

        # F2: Operator suggestions
        sub("F2: Operator Suggestions (Drone 4, Frame 200)")
        r = await c.post(f"{RESCUE}/api/rescue/operator_suggestions", json={"drone_id": 4, "frame_num": 200})
        os_resp = r.json()
        print(f"[+] Priority: {os_resp['priority_level']}")
        print(f"[+] Assessment: {os_resp['situation_assessment'][:200]}...")
        print(f"[+] Actions: {len(os_resp['operator_actions'])}")
        for act in os_resp["operator_actions"][:3]:
            print(f"    → [{act.get('priority','?')}] {act.get('action','')[:100]}")
        print(f"[+] Resources: {os_resp['resource_requests']}")

        header("FLOW COMPLETE ")
        print("All 3 phases tested successfully.")


if __name__ == "__main__":
    asyncio.run(run())
