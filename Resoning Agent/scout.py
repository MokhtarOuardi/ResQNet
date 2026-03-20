import os
import json
import base64
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_VLM_MODEL = os.getenv("OPENROUTER_VLM_MODEL", "google/gemma-3-4b-it:free")
OPENROUTER_LLM_MODEL = os.getenv("OPENROUTER_LLM_MODEL", "stepfun/step-3.5-flash:free")
OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"
DATASET_PATH = Path(os.getenv("DATASET_PATH", str(Path(__file__).parent.parent / "Dataset")))

app = FastAPI(title="ResQNet Scout", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

scout_context: list[dict] = []
zone_data: dict = {}
detection_cache: dict = {}

def encode_image_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def vlm_chat(messages: list[dict], temperature: float = 0.3) -> str:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set")
    async with httpx.AsyncClient(timeout=120.0) as http:
        resp = await http.post(
            OPENROUTER_BASE,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": OPENROUTER_VLM_MODEL, "messages": messages, "temperature": temperature},
        )
        if resp.status_code != 200:
            logger.error(f"VLM error {resp.status_code}: {resp.text}")
            raise HTTPException(status_code=502, detail=f"VLM request failed: {resp.status_code}")
        return resp.json()["choices"][0]["message"]["content"]


async def llm_chat(messages: list[dict], temperature: float = 0.3) -> str:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY not set")
    async with httpx.AsyncClient(timeout=120.0) as http:
        resp = await http.post(
            OPENROUTER_BASE,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": OPENROUTER_LLM_MODEL, "messages": messages, "temperature": temperature},
        )
        if resp.status_code != 200:
            logger.error(f"LLM error {resp.status_code}: {resp.text}")
            raise HTTPException(status_code=502, detail=f"LLM request failed: {resp.status_code}")
        return resp.json()["choices"][0]["message"]["content"]


def parse_json_response(text: str) -> dict | list:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return json.loads(cleaned)


def parse_drone_log(drone_id: int) -> list[dict]:
    log_path = DATASET_PATH / str(drone_id) / "log.txt"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"Log not found: {log_path}")
    entries = []
    with open(log_path, "r") as f:
        lines = f.readlines()
    for line in lines[1:]:  # skip header
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 6:
            entries.append({
                "frame_num": int(parts[0]),
                "timestamp": parts[1],
                "gps_x": float(parts[2]),
                "gps_y": float(parts[3]),
                "altitude": float(parts[4]),
                "battery": float(parts[-1]),
            })
    return entries


class DetectRequest(BaseModel):
    drone_id: int = Field(description="Drone ID (1-4)")
    frame_num: int = Field(description="Frame number to analyze")

class DetectResponse(BaseModel):
    drone_id: int
    frame_num: int
    detections: dict = Field(description="Detected objects: buildings, people, fire, smoke, flood")
    vlm_description: str = Field(description="VLM scene description")
    gps: Optional[dict] = None

class SplitZonesRequest(BaseModel):
    grid_size: int = Field(4, description="NxN grid to split the zone into")

class ZoneInfo(BaseModel):
    zone_id: str
    bounds: dict = Field(description="min_x, max_x, min_y, max_y")
    drone_frames: list[dict] = Field(description="List of {drone_id, frame_num, gps_x, gps_y}")
    frame_count: int

class SplitZonesResponse(BaseModel):
    total_zones: int
    grid_size: int
    bounds: dict
    zones: list[ZoneInfo]

class ZoneIdRequest(BaseModel):
    zone_id: str = Field(description="Zone ID like 'Z_0_0'")

class DangerRatingResponse(BaseModel):
    zone_id: str
    danger_rating: float = Field(description="0.0 (safe) to 1.0 (extreme)")
    hazards: list[str]
    reasoning: str

class DensityResponse(BaseModel):
    zone_id: str
    estimated_people: int
    density_level: str = Field(description="none, low, medium, high, critical")
    reasoning: str

class PriorityResponse(BaseModel):
    zone_id: str
    priority: int = Field(description="1 (highest) to 10 (lowest)")
    reasoning: str

class StrategyRequest(BaseModel):
    context: Optional[str] = Field(None, description="Additional context from monitor or previous analysis")

class StrategyResponse(BaseModel):
    strategy: str
    phases: list[dict]
    resource_allocation: dict

class EscapeRouteResponse(BaseModel):
    safety_zones: list[dict]
    escape_routes: list[dict]
    reasoning: str


# F1 — Detect from drone feed (YOLO + VLM)
@app.post("/api/scout/detect", response_model=DetectResponse)
async def detect_frame(request: DetectRequest):
    frame_path = DATASET_PATH / str(request.drone_id) / f"frame_{request.frame_num}.jpg"
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"Frame not found: {frame_path}")

    img_b64 = encode_image_b64(str(frame_path))

    # Get GPS for this frame
    log_entries = parse_drone_log(request.drone_id)
    gps = None
    for e in log_entries:
        if e["frame_num"] == request.frame_num:
            gps = {"x": e["gps_x"], "y": e["gps_y"], "altitude": e["altitude"]}
            break

    # VLM analysis
    prompt = """Analyze this drone aerial image for a search-and-rescue operation.
Detect and count ALL of the following:
- buildings (intact, damaged, collapsed)
- people (visible individuals or groups)
- fire (active flames or burning areas)
- smoke (visible smoke plumes)
- flood (water covering roads, fields, or buildings)
- vehicles (cars, trucks, emergency vehicles)
- debris (rubble, fallen trees, destruction)
- roads (accessible, blocked, flooded)

Respond as JSON:
{
  "buildings": {"count": N, "intact": N, "damaged": N, "collapsed": N},
  "people": {"count": N, "groups": N, "description": "..."},
  "fire": {"detected": bool, "severity": "none/minor/major", "description": "..."},
  "smoke": {"detected": bool, "severity": "none/minor/major"},
  "flood": {"detected": bool, "severity": "none/minor/major", "description": "..."},
  "vehicles": {"count": N, "types": []},
  "debris": {"detected": bool, "severity": "none/minor/major"},
  "roads": {"accessible": bool, "blocked": bool, "flooded": bool},
  "scene_description": "2-3 sentence description of what you see"
}
Respond with ONLY valid JSON, no markdown."""

    vlm_response = await vlm_chat([
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ]},
    ])

    try:
        detections = parse_json_response(vlm_response)
    except json.JSONDecodeError:
        detections = {"raw_response": vlm_response[:500], "error": "Failed to parse VLM response"}

    scene_desc = detections.get("scene_description", vlm_response[:300])

    # Cache detection
    cache_key = f"d{request.drone_id}_f{request.frame_num}"
    detection_cache[cache_key] = {"detections": detections, "gps": gps}

    return DetectResponse(
        drone_id=request.drone_id,
        frame_num=request.frame_num,
        detections=detections,
        vlm_description=scene_desc if isinstance(scene_desc, str) else json.dumps(scene_desc),
        gps=gps,
    )


# F2 — Split scouting zone into grid zones
@app.post("/api/scout/split_zones", response_model=SplitZonesResponse)
async def split_zones(request: SplitZonesRequest):
    global zone_data

    all_entries = []
    for drone_id in range(1, 5):
        try:
            entries = parse_drone_log(drone_id)
            for e in entries:
                e["drone_id"] = drone_id
            all_entries.extend(entries)
        except Exception as ex:
            logger.warning(f"Could not load drone {drone_id} log: {ex}")

    if not all_entries:
        raise HTTPException(status_code=404, detail="No drone logs found")

    # Compute global bounds
    min_x = min(e["gps_x"] for e in all_entries)
    max_x = max(e["gps_x"] for e in all_entries)
    min_y = min(e["gps_y"] for e in all_entries)
    max_y = max(e["gps_y"] for e in all_entries)

    n = request.grid_size
    dx = (max_x - min_x) / n
    dy = (max_y - min_y) / n

    zones: list[ZoneInfo] = []
    zone_data = {}

    for i in range(n):
        for j in range(n):
            zx_min = min_x + i * dx
            zx_max = min_x + (i + 1) * dx
            zy_min = min_y + j * dy
            zy_max = min_y + (j + 1) * dy
            zone_id = f"Z_{i}_{j}"

            # Find frames in this zone
            frames_in_zone = []
            for e in all_entries:
                if zx_min <= e["gps_x"] < zx_max and zy_min <= e["gps_y"] < zy_max:
                    frames_in_zone.append({
                        "drone_id": e["drone_id"],
                        "frame_num": e["frame_num"],
                        "gps_x": e["gps_x"],
                        "gps_y": e["gps_y"],
                    })

            zone_info = ZoneInfo(
                zone_id=zone_id,
                bounds={"min_x": zx_min, "max_x": zx_max, "min_y": zy_min, "max_y": zy_max},
                drone_frames=frames_in_zone,
                frame_count=len(frames_in_zone),
            )
            zones.append(zone_info)
            zone_data[zone_id] = zone_info.model_dump()

    return SplitZonesResponse(
        total_zones=len(zones),
        grid_size=n,
        bounds={"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y},
        zones=zones,
    )


# F3 — Danger rating per zone (VLM)
@app.post("/api/scout/danger_rating", response_model=DangerRatingResponse)
async def danger_rating(request: ZoneIdRequest):
    if request.zone_id not in zone_data:
        raise HTTPException(status_code=404, detail=f"Zone {request.zone_id} not found. Run split_zones first.")

    zone = zone_data[request.zone_id]
    frames = zone["drone_frames"]
    if not frames:
        return DangerRatingResponse(zone_id=request.zone_id, danger_rating=0.0, hazards=[], reasoning="No frames in this zone")

    # Sample up to 3 frames for VLM analysis
    sample = frames[:: max(1, len(frames) // 3)][:3]
    image_contents = []
    for fr in sample:
        fp = DATASET_PATH / str(fr["drone_id"]) / f"frame_{fr['frame_num']}.jpg"
        if fp.exists():
            img_b64 = encode_image_b64(str(fp))
            image_contents.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})

    if not image_contents:
        return DangerRatingResponse(zone_id=request.zone_id, danger_rating=0.0, hazards=[], reasoning="No valid frames")

    prompt = f"""You are assessing danger in zone {request.zone_id} of a disaster area.
Zone bounds: {json.dumps(zone['bounds'])}
Frames analyzed: {len(image_contents)}

Analyze these aerial drone images and rate the danger level for rescue teams.
Consider: fire, flooding, structural collapse, toxic smoke, debris, terrain accessibility.

Respond as JSON:
{{
  "danger_rating": 0.0-1.0 (0=safe, 1=extreme danger),
  "hazards": ["list", "of", "identified", "hazards"],
  "reasoning": "Your detailed reasoning"
}}
Respond with ONLY valid JSON."""

    content = [{"type": "text", "text": prompt}] + image_contents
    vlm_response = await vlm_chat([{"role": "user", "content": content}])

    try:
        result = parse_json_response(vlm_response)
    except json.JSONDecodeError:
        result = {"danger_rating": 0.5, "hazards": ["unknown"], "reasoning": vlm_response[:300]}

    return DangerRatingResponse(zone_id=request.zone_id, **result)


# F4 — People density heatmap per zone (VLM + Detection)
@app.post("/api/scout/density", response_model=DensityResponse)
async def density_estimation(request: ZoneIdRequest):
    if request.zone_id not in zone_data:
        raise HTTPException(status_code=404, detail=f"Zone {request.zone_id} not found. Run split_zones first.")

    zone = zone_data[request.zone_id]
    frames = zone["drone_frames"]
    if not frames:
        return DensityResponse(zone_id=request.zone_id, estimated_people=0, density_level="none", reasoning="No frames")

    sample = frames[:: max(1, len(frames) // 3)][:3]
    image_contents = []
    for fr in sample:
        fp = DATASET_PATH / str(fr["drone_id"]) / f"frame_{fr['frame_num']}.jpg"
        if fp.exists():
            img_b64 = encode_image_b64(str(fp))
            image_contents.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})

    if not image_contents:
        return DensityResponse(zone_id=request.zone_id, estimated_people=0, density_level="none", reasoning="No valid frames")

    prompt = f"""Analyze these aerial drone images from zone {request.zone_id} of a disaster area.
Estimate the number of people visible or likely present (consider buildings, vehicles, crowd patterns).
This is for search-and-rescue prioritization.

Respond as JSON:
{{
  "estimated_people": integer estimate,
  "density_level": "none" | "low" | "medium" | "high" | "critical",
  "reasoning": "How you estimated this — visible people, building occupancy estimates, vehicle count, etc."
}}
Respond with ONLY valid JSON."""

    content = [{"type": "text", "text": prompt}] + image_contents
    vlm_response = await vlm_chat([{"role": "user", "content": content}])

    try:
        result = parse_json_response(vlm_response)
    except json.JSONDecodeError:
        result = {"estimated_people": 0, "density_level": "unknown", "reasoning": vlm_response[:300]}

    return DensityResponse(zone_id=request.zone_id, **result)


# F5 — Rescue priority per zone (VLM + LLM)
@app.post("/api/scout/priority", response_model=PriorityResponse)
async def rescue_priority(request: ZoneIdRequest):
    if request.zone_id not in zone_data:
        raise HTTPException(status_code=404, detail=f"Zone {request.zone_id} not found. Run split_zones first.")

    zone = zone_data[request.zone_id]
    frames = zone["drone_frames"]
    if not frames:
        return PriorityResponse(zone_id=request.zone_id, priority=10, reasoning="No frames — lowest priority")

    sample = frames[:: max(1, len(frames) // 3)][:3]
    image_contents = []
    for fr in sample:
        fp = DATASET_PATH / str(fr["drone_id"]) / f"frame_{fr['frame_num']}.jpg"
        if fp.exists():
            img_b64 = encode_image_b64(str(fp))
            image_contents.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})

    # Include any cached context
    ctx = ""
    if scout_context:
        ctx = f"\n\nPrevious scouting context:\n{json.dumps(scout_context[-3:], indent=2)}"

    prompt = f"""You are a rescue operation commander evaluating zone {request.zone_id}.
Zone bounds: {json.dumps(zone['bounds'])}
Frames in zone: {zone['frame_count']}
{ctx}

Analyze these aerial images and assign a RESCUE PRIORITY from 1 (HIGHEST — rescue immediately) to 10 (LOWEST).
Consider:
- Number of people at risk
- Danger level (fire, flood, collapse)
- Accessibility for rescue teams
- Time sensitivity (worsening conditions)

Respond as JSON:
{{
  "priority": 1-10,
  "reasoning": "Why this priority — people at risk, danger level, accessibility"
}}
Respond with ONLY valid JSON."""

    content = [{"type": "text", "text": prompt}] + image_contents
    vlm_response = await vlm_chat([{"role": "user", "content": content}])

    try:
        result = parse_json_response(vlm_response)
    except json.JSONDecodeError:
        result = {"priority": 5, "reasoning": vlm_response[:300]}

    # Update context
    scout_context.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "rescue_priority",
        "zone_id": request.zone_id,
        "priority": result["priority"],
    })

    return PriorityResponse(zone_id=request.zone_id, **result)


# F6 — Generate rescue strategy (LLM)
@app.post("/api/scout/strategy", response_model=StrategyResponse)
async def rescue_strategy(request: StrategyRequest):
    # Gather all available zone data and context
    zone_summary = []
    for zid, zdata in zone_data.items():
        zone_summary.append({"zone_id": zid, "frame_count": zdata["frame_count"], "bounds": zdata["bounds"]})

    ctx = ""
    if request.context:
        ctx = f"\nAdditional context from monitoring:\n{request.context}"
    if scout_context:
        ctx += f"\n\nScouting analysis so far:\n{json.dumps(scout_context, indent=2)}"

    prompt = f"""You are the chief strategist for ResQNet, a search-and-rescue platform.
Based on the drone scouting data, generate a comprehensive rescue strategy.

Zone data:
{json.dumps(zone_summary, indent=2)}
{ctx}

Generate a detailed rescue strategy as JSON:
{{
  "strategy": "Executive summary of the rescue strategy (3-5 sentences)",
  "phases": [
    {{
      "phase": 1,
      "name": "Phase name",
      "description": "What to do",
      "zones": ["Z_0_0", ...],
      "resources": ["resource1", ...],
      "estimated_time": "X hours"
    }}
  ],
  "resource_allocation": {{
    "medical_teams": N,
    "rescue_squads": N,
    "vehicles": ["type1", ...],
    "equipment": ["item1", ...],
    "estimated_personnel": N
  }}
}}
Respond with ONLY valid JSON."""

    llm_response = await llm_chat([
        {"role": "system", "content": "You are an expert search-and-rescue strategist. Respond only with valid JSON."},
        {"role": "user", "content": prompt},
    ])

    try:
        result = parse_json_response(llm_response)
    except json.JSONDecodeError:
        result = {"strategy": llm_response[:500], "phases": [], "resource_allocation": {}}

    scout_context.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "rescue_strategy",
        "strategy_summary": result.get("strategy", "")[:200],
    })

    return StrategyResponse(**result)


# F7 — Escape routes / safety zones (LLM)
@app.post("/api/scout/escape_routes", response_model=EscapeRouteResponse)
async def escape_routes():
    zone_summary = []
    for zid, zdata in zone_data.items():
        zone_summary.append({"zone_id": zid, "frame_count": zdata["frame_count"], "bounds": zdata["bounds"]})

    ctx = ""
    if scout_context:
        ctx = f"\n\nAll scouting context:\n{json.dumps(scout_context, indent=2)}"

    prompt = f"""You are a safety/evacuation expert for ResQNet search-and-rescue operations.
Based on the scouting data, generate escape routes and safety zones.

Zone data:
{json.dumps(zone_summary, indent=2)}
{ctx}

Generate as JSON:
{{
  "safety_zones": [
    {{
      "zone_id": "Z_X_Y",
      "name": "Safety Zone Name",
      "description": "Why this zone is safe — terrain, distance from hazards",
      "capacity": estimated number of people,
      "gps_center": {{"x": float, "y": float}}
    }}
  ],
  "escape_routes": [
    {{
      "from_zone": "Z_X_Y",
      "to_safety_zone": "Safety Zone Name",
      "route_description": "Step-by-step directions",
      "distance_estimate": "X km",
      "hazards_on_route": ["hazard1", ...],
      "suitability": "walking" | "vehicle" | "helicopter"
    }}
  ],
  "reasoning": "Overall reasoning for safety zone and route selection"
}}
Respond with ONLY valid JSON."""

    llm_response = await llm_chat([
        {"role": "system", "content": "You are an evacuation planning expert. Respond only with valid JSON."},
        {"role": "user", "content": prompt},
    ])

    try:
        result = parse_json_response(llm_response)
    except json.JSONDecodeError:
        result = {"safety_zones": [], "escape_routes": [], "reasoning": llm_response[:500]}

    return EscapeRouteResponse(**result)


# api

@app.get("/api/scout/context")
async def get_context():
    return {"total_entries": len(scout_context), "context": scout_context}

@app.get("/api/scout/zones")
async def get_zones():
    return {"total_zones": len(zone_data), "zones": zone_data}

@app.delete("/api/scout/context")
async def clear_context():
    scout_context.clear()
    return {"message": "Scout context cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8001)
