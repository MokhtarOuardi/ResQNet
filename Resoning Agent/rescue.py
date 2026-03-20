import os
import json
import base64
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

app = FastAPI(title="ResQNet Rescue", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

rescue_context: list[dict] = []


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
            raise HTTPException(status_code=502, detail=f"LLM request failed: {resp.status_code}")
        return resp.json()["choices"][0]["message"]["content"]


def parse_json_response(text: str) -> dict | list:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return json.loads(cleaned)


class RescueRequest(BaseModel):
    drone_id: int = Field(description="Drone ID (1-4)")
    frame_num: int = Field(description="Frame number to analyze")
    additional_context: Optional[str] = Field(None, description="Extra context from scout/search phases")

class SafetyInstructionResponse(BaseModel):
    drone_id: int
    frame_num: int
    scene_description: str = Field(description="VLM description of the scene")
    persons_identified: list[dict] = Field(description="People identified and their situation")
    safety_instructions: list[dict] = Field(description="Per-person or group safety instructions")
    general_guidelines: str = Field(description="General safety guidelines for all persons in the area")

class OperatorSuggestionResponse(BaseModel):
    drone_id: int
    frame_num: int
    scene_description: str
    situation_assessment: str = Field(description="Assessment of the current situation")
    operator_actions: list[dict] = Field(description="Suggested actions for the operator")
    resource_requests: list[str] = Field(description="Resources the operator should request")
    priority_level: str = Field(description="low, medium, high, critical")


# F1 — Safety instructions for identified persons
@app.post("/api/rescue/safety_instructions", response_model=SafetyInstructionResponse)
async def safety_instructions(request: RescueRequest):
    frame_path = DATASET_PATH / str(request.drone_id) / f"frame_{request.frame_num}.jpg"
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"Frame not found: {frame_path}")

    img_b64 = encode_image_b64(str(frame_path))

    # Step 1: VLM — describe the scene and identify persons
    vlm_prompt = """Analyze this aerial drone image from a search-and-rescue operation.
Describe the scene in detail focusing on:
- People visible: their location, posture, apparent condition, what they are doing
- Hazards near them: fire, water, debris, structural damage
- Environment: terrain, weather conditions, accessibility
- Any signs of distress or injury

Provide a detailed text description, be specific about each person or group you see."""

    scene_description = await vlm_chat([{"role": "user", "content": [
        {"type": "text", "text": vlm_prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
    ]}])

    # Step 2: LLM — generate safety instructions based on VLM description
    ctx = ""
    if request.additional_context:
        ctx = f"\nAdditional context: {request.additional_context}"
    if rescue_context:
        ctx += f"\nPrevious rescue context: {json.dumps(rescue_context[-3:], indent=2)}"

    llm_prompt = f"""You are a rescue safety officer for ResQNet.
Based on the following aerial drone scene description, generate safety instructions.

SCENE DESCRIPTION:
{scene_description}
{ctx}

Generate as JSON:
{{
  "persons_identified": [
    {{
      "id": "person_1",
      "location": "where in the scene",
      "condition": "apparent condition",
      "immediate_risk": "what danger they face"
    }}
  ],
  "safety_instructions": [
    {{
      "target": "person_1 or 'all_persons'",
      "instruction": "Clear, simple instruction (as if spoken via loudspeaker from drone)",
      "priority": "immediate" | "soon" | "when_safe",
      "reason": "why this instruction"
    }}
  ],
  "general_guidelines": "General safety guidelines for everyone in the area (2-3 sentences, simple language)"
}}
Instructions should be clear, actionable, and appropriate for people in distress.
Respond with ONLY valid JSON."""

    llm_response = await llm_chat([
        {"role": "system", "content": "You are an expert rescue safety officer. Generate clear, life-saving instructions. Respond only with valid JSON."},
        {"role": "user", "content": llm_prompt},
    ])

    try:
        result = parse_json_response(llm_response)
    except json.JSONDecodeError:
        result = {
            "persons_identified": [],
            "safety_instructions": [{"target": "all_persons", "instruction": llm_response[:300], "priority": "immediate", "reason": "auto-generated"}],
            "general_guidelines": "Stay calm. Move to higher ground if flooding. Avoid damaged structures.",
        }

    rescue_context.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "safety_instructions",
        "drone_id": request.drone_id,
        "frame_num": request.frame_num,
        "persons_count": len(result.get("persons_identified", [])),
    })

    return SafetyInstructionResponse(
        drone_id=request.drone_id,
        frame_num=request.frame_num,
        scene_description=scene_description,
        **result,
    )


# F2 — Operator suggestions
@app.post("/api/rescue/operator_suggestions", response_model=OperatorSuggestionResponse)
async def operator_suggestions(request: RescueRequest):
    frame_path = DATASET_PATH / str(request.drone_id) / f"frame_{request.frame_num}.jpg"
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"Frame not found: {frame_path}")

    img_b64 = encode_image_b64(str(frame_path))

    # Step 1: VLM — describe the scene
    vlm_prompt = """Analyze this aerial drone image from a search-and-rescue operation.
Provide a tactical assessment for the rescue operator:
- Terrain and accessibility (roads, paths, obstacles)
- Number and condition of people visible
- Active hazards (fire, flood, structural collapse, smoke)
- Available landing zones or staging areas
- Visible resources (vehicles, boats, buildings that could serve as shelter)

Be precise and tactical in your description."""

    scene_description = await vlm_chat([{"role": "user", "content": [
        {"type": "text", "text": vlm_prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
    ]}])

    # Step 2: LLM — generate operator suggestions
    ctx = ""
    if request.additional_context:
        ctx = f"\nAdditional context: {request.additional_context}"
    if rescue_context:
        ctx += f"\nPrevious rescue context: {json.dumps(rescue_context[-3:], indent=2)}"

    llm_prompt = f"""You are a rescue operations advisor for ResQNet.
Based on the drone's tactical assessment, generate actionable suggestions for the rescue operator.

TACTICAL ASSESSMENT:
{scene_description}
{ctx}

Generate as JSON:
{{
  "situation_assessment": "Brief assessment of the situation (2-3 sentences)",
  "operator_actions": [
    {{
      "action": "What the operator should do",
      "priority": "immediate" | "high" | "medium" | "low",
      "reason": "Why this action",
      "estimated_time": "How long this might take"
    }}
  ],
  "resource_requests": ["List of resources to request: ambulances, fire trucks, boats, helicopters, etc."],
  "priority_level": "low" | "medium" | "high" | "critical"
}}
Respond with ONLY valid JSON."""

    llm_response = await llm_chat([
        {"role": "system", "content": "You are an expert rescue operations advisor. Respond only with valid JSON."},
        {"role": "user", "content": llm_prompt},
    ])

    try:
        result = parse_json_response(llm_response)
    except json.JSONDecodeError:
        result = {
            "situation_assessment": llm_response[:300],
            "operator_actions": [],
            "resource_requests": [],
            "priority_level": "medium",
        }

    rescue_context.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "operator_suggestions",
        "drone_id": request.drone_id,
        "frame_num": request.frame_num,
        "priority": result.get("priority_level"),
    })

    return OperatorSuggestionResponse(
        drone_id=request.drone_id,
        frame_num=request.frame_num,
        scene_description=scene_description,
        **result,
    )


# api

@app.get("/api/rescue/context")
async def get_context():
    return {"total_entries": len(rescue_context), "context": rescue_context}

@app.delete("/api/rescue/context")
async def clear_context():
    rescue_context.clear()
    return {"message": "Rescue context cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8003)
