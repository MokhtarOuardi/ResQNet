import os
import json
import base64
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
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

app = FastAPI(title="ResQNet Search", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

search_context: list[dict] = []
alarms: list[dict] = []
last_processed_frame: dict = {1: -1, 2: -1, 3: -1, 4: -1}


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


def parse_json_response(text: str) -> dict | list:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return json.loads(cleaned)


class UpdateRequest(BaseModel):
    drone_id: int = Field(description="Drone ID (1-4)")
    start_frame: Optional[int] = Field(None, description="Start from this frame (default: last processed + 1)")
    num_frames: int = Field(5, description="How many frames to process in this batch")

class UpdateResult(BaseModel):
    drone_id: int
    frames_processed: list[int]
    detections_summary: list[dict]
    timestamp: str

class MedicalRequest(BaseModel):
    drone_id: int = Field(description="Drone ID (1-4)")
    frame_num: int = Field(description="Frame number to analyze")

class MedicalResponse(BaseModel):
    drone_id: int
    frame_num: int
    emergency_detected: bool
    severity: str = Field(description="none, minor, serious, critical, life_threatening")
    alarm: bool = Field(description="True if operator should be alerted immediately")
    details: dict = Field(description="Detected medical emergencies")
    reasoning: str

class ThreatRequest(BaseModel):
    drone_id: int = Field(description="Drone ID (1-4)")
    frame_num: int = Field(description="Frame number to analyze")

class ThreatResponse(BaseModel):
    drone_id: int
    frame_num: int
    threat_detected: bool
    threat_level: str = Field(description="none, low, medium, high, critical")
    alarm: bool = Field(description="True if operator action is required")
    threats: list[dict] = Field(description="List of detected threats")
    reasoning: str


# F1 — Continuous update of scouting maps / detections
@app.post("/api/search/update", response_model=UpdateResult)
async def continuous_update(request: UpdateRequest):
    drone_dir = DATASET_PATH / str(request.drone_id)
    if not drone_dir.exists():
        raise HTTPException(status_code=404, detail=f"Drone {request.drone_id} data not found")

    start = request.start_frame if request.start_frame is not None else last_processed_frame[request.drone_id] + 1
    frames_to_process = []
    for i in range(start, start + request.num_frames):
        fp = drone_dir / f"frame_{i}.jpg"
        if fp.exists():
            frames_to_process.append(i)

    if not frames_to_process:
        return UpdateResult(
            drone_id=request.drone_id,
            frames_processed=[],
            detections_summary=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    detections_summary = []
    for frame_num in frames_to_process:
        fp = drone_dir / f"frame_{frame_num}.jpg"
        img_b64 = encode_image_b64(str(fp))

        prompt = """Quickly analyze this drone aerial image for search-and-rescue updates.
Detect changes or notable observations:
- People (new sightings, movement, groups)
- Hazard changes (fire spreading, water rising, new collapse)
- Vehicles or rescue teams arriving
- Accessibility changes (roads cleared or blocked)

Respond as JSON:
{
  "people_visible": integer,
  "hazard_changes": "description of any changes or 'no change'",
  "notable": "any notable observation",
  "urgency": "low" | "medium" | "high"
}
Respond with ONLY valid JSON."""

        vlm_response = await vlm_chat([{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ]}])

        try:
            detection = parse_json_response(vlm_response)
        except json.JSONDecodeError:
            detection = {"raw": vlm_response[:200], "error": "parse_failed"}

        detection["frame_num"] = frame_num
        detections_summary.append(detection)
        last_processed_frame[request.drone_id] = frame_num

    search_context.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "continuous_update",
        "drone_id": request.drone_id,
        "frames": frames_to_process,
        "summary": f"Processed {len(frames_to_process)} frames from drone {request.drone_id}",
    })

    return UpdateResult(
        drone_id=request.drone_id,
        frames_processed=frames_to_process,
        detections_summary=detections_summary,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# F2 — Detect medical emergency from drone frame
@app.post("/api/search/medical", response_model=MedicalResponse)
async def detect_medical(request: MedicalRequest):
    frame_path = DATASET_PATH / str(request.drone_id) / f"frame_{request.frame_num}.jpg"
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"Frame not found: {frame_path}")

    img_b64 = encode_image_b64(str(frame_path))

    prompt = """You are a medical emergency detection AI for a search-and-rescue drone system.
Analyze this aerial drone image for ANY signs of medical emergencies:

Look for:
- People lying on the ground / not moving
- People waving for help or in distress
- Injured persons (visible injuries, blood)
- People trapped under debris or in water
- Elderly or children in danger
- Groups gathered around someone (bystander effect = possible injury)
- Vehicles that appear to have been in accidents

Respond as JSON:
{
  "emergency_detected": true/false,
  "severity": "none" | "minor" | "serious" | "critical" | "life_threatening",
  "alarm": true/false (true if operator MUST be notified immediately),
  "details": {
    "injured_count": integer estimate,
    "trapped_count": integer estimate,
    "type": "description of medical situation",
    "location_in_frame": "where in the image",
    "recommended_response": "what medical resources are needed"
  },
  "reasoning": "Your analysis"
}
Respond with ONLY valid JSON."""

    vlm_response = await vlm_chat([{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
    ]}])

    try:
        result = parse_json_response(vlm_response)
    except json.JSONDecodeError:
        result = {
            "emergency_detected": False, "severity": "unknown", "alarm": False,
            "details": {"error": "parse_failed"}, "reasoning": vlm_response[:300],
        }

    # Auto-add to alarms if alarm triggered
    if result.get("alarm"):
        alarm_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "MEDICAL_EMERGENCY",
            "drone_id": request.drone_id,
            "frame_num": request.frame_num,
            "severity": result.get("severity"),
            "details": result.get("details"),
        }
        alarms.append(alarm_entry)
        logger.warning(f"🚨 MEDICAL ALARM: Drone {request.drone_id} Frame {request.frame_num} — {result.get('severity')}")

    return MedicalResponse(drone_id=request.drone_id, frame_num=request.frame_num, **result)


# F3 — Detect threats from drone frame
@app.post("/api/search/threats", response_model=ThreatResponse)
async def detect_threats(request: ThreatRequest):
    frame_path = DATASET_PATH / str(request.drone_id) / f"frame_{request.frame_num}.jpg"
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"Frame not found: {frame_path}")

    img_b64 = encode_image_b64(str(frame_path))

    prompt = """You are a threat/risk detection AI for a search-and-rescue drone system.
Analyze this aerial drone image for ANY threats or risks that require operator attention:

Look for:
- Structural instability (buildings about to collapse, leaning structures)
- Fire spreading toward populated areas
- Rising water levels / flash flood risk
- Gas leaks or chemical hazards (discoloration, unusual patterns)
- Downed power lines or electrical hazards
- Unstable terrain (landslide risk, sinkholes)
- Blocked evacuation routes
- Secondary disaster risk (aftershock damage, dam failure indicators)

Respond as JSON:
{
  "threat_detected": true/false,
  "threat_level": "none" | "low" | "medium" | "high" | "critical",
  "alarm": true/false (true if operator MUST act NOW),
  "threats": [
    {
      "type": "threat type",
      "description": "what you see",
      "location_in_frame": "where",
      "risk_to": "who/what is at risk",
      "recommended_action": "what should be done"
    }
  ],
  "reasoning": "Your analysis"
}
Respond with ONLY valid JSON."""

    vlm_response = await vlm_chat([{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
    ]}])

    try:
        result = parse_json_response(vlm_response)
    except json.JSONDecodeError:
        result = {
            "threat_detected": False, "threat_level": "unknown", "alarm": False,
            "threats": [], "reasoning": vlm_response[:300],
        }

    if result.get("alarm"):
        alarm_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "THREAT_DETECTED",
            "drone_id": request.drone_id,
            "frame_num": request.frame_num,
            "threat_level": result.get("threat_level"),
            "threats": result.get("threats"),
        }
        alarms.append(alarm_entry)
        logger.warning(f"⚠️ THREAT ALARM: Drone {request.drone_id} Frame {request.frame_num} — {result.get('threat_level')}")

    return ThreatResponse(drone_id=request.drone_id, frame_num=request.frame_num, **result)


# api

@app.get("/api/search/alarms")
async def get_alarms():
    return {"total": len(alarms), "alarms": alarms}

@app.delete("/api/search/alarms")
async def clear_alarms():
    alarms.clear()
    return {"message": "Alarms cleared"}

@app.get("/api/search/context")
async def get_context():
    return {"total_entries": len(search_context), "context": search_context}

@app.get("/api/search/status")
async def get_status():
    return {
        "last_processed_frame": last_processed_frame,
        "active_alarms": len(alarms),
        "context_entries": len(search_context),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8002)
