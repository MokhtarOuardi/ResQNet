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
DRONE_CONTROLLER_URL = os.getenv("DRONE_CONTROLLER_URL", "http://127.0.0.1:5000")

# Module API base URLs (each module runs on its own port)
MONITOR_URL = os.getenv("MONITOR_URL", "http://localhost:8000")
SCOUT_URL = os.getenv("SCOUT_URL", "http://localhost:8001")
SEARCH_URL = os.getenv("SEARCH_URL", "http://localhost:8002")
RESCUE_URL = os.getenv("RESCUE_URL", "http://localhost:8003")

app = FastAPI(title="ResQNet Agent", description="Unified AI Agent for Search & Rescue", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

conversation_history: list[dict] = []

# Tool definitions for the LLM 

TOOLS = [
    # Monitor 
    {
        "type": "function",
        "function": {
            "name": "monitor_scan_trends",
            "description": "Scan X/Twitter trending topics for potential disaster-related events. Returns classified alerts with reasoning.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_analyze_tag",
            "description": "Deep-dive into a specific hashtag to extract rescue-relevant information from tweets.",
            "parameters": {
                "type": "object",
                "properties": {"hashtag": {"type": "string", "description": "Hashtag to analyze (with or without #)"}},
                "required": ["hashtag"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_update_context",
            "description": "Append new reasoning to the monitor's persistent context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string", "description": "New reasoning text to append"},
                    "source": {"type": "string", "description": "Source label", "default": "agent"},
                },
                "required": ["reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_get_alerts",
            "description": "Get the latest cached scan results and alerts from the monitor.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    #  Scout 
    {
        "type": "function",
        "function": {
            "name": "scout_detect",
            "description": "Analyze a specific drone frame using VLM to detect buildings, people, fire, smoke, flood, vehicles, and debris.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Drone ID (1-4)"},
                    "frame_num": {"type": "integer", "description": "Frame number to analyze"},
                },
                "required": ["drone_id", "frame_num"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scout_split_zones",
            "description": "Parse all drone logs and split the scouting area into an NxN grid of zones, mapping frames to each zone.",
            "parameters": {
                "type": "object",
                "properties": {"grid_size": {"type": "integer", "description": "Grid size (NxN)", "default": 4}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scout_danger_rating",
            "description": "Get VLM-based danger rating (0-1) for a specific zone. Requires split_zones to have been called first.",
            "parameters": {
                "type": "object",
                "properties": {"zone_id": {"type": "string", "description": "Zone ID like 'Z_0_0'"}},
                "required": ["zone_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scout_density",
            "description": "Estimate people density for a specific zone using VLM analysis.",
            "parameters": {
                "type": "object",
                "properties": {"zone_id": {"type": "string", "description": "Zone ID"}},
                "required": ["zone_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scout_priority",
            "description": "Get rescue priority rating (1-10) for a zone. 1=highest priority.",
            "parameters": {
                "type": "object",
                "properties": {"zone_id": {"type": "string", "description": "Zone ID"}},
                "required": ["zone_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scout_strategy",
            "description": "Generate a comprehensive rescue strategy with phases and resource allocation based on all zone data.",
            "parameters": {
                "type": "object",
                "properties": {"context": {"type": "string", "description": "Additional context"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scout_escape_routes",
            "description": "Generate escape routes and identify safety zones based on scouting data.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    #  Search 
    {
        "type": "function",
        "function": {
            "name": "search_update",
            "description": "Process a batch of new drone frames for continuous map/detection updates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Drone ID (1-4)"},
                    "num_frames": {"type": "integer", "description": "How many frames to process", "default": 5},
                    "start_frame": {"type": "integer", "description": "Start frame number (optional)"},
                },
                "required": ["drone_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_medical",
            "description": "Analyze a drone frame for medical emergencies. Triggers alarm if critical.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Drone ID (1-4)"},
                    "frame_num": {"type": "integer", "description": "Frame number"},
                },
                "required": ["drone_id", "frame_num"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_threats",
            "description": "Analyze a drone frame for threats/risks requiring operator attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Drone ID (1-4)"},
                    "frame_num": {"type": "integer", "description": "Frame number"},
                },
                "required": ["drone_id", "frame_num"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_get_alarms",
            "description": "Get all active alarms from the search module.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    #  Rescue 
    {
        "type": "function",
        "function": {
            "name": "rescue_safety_instructions",
            "description": "Generate safety instructions for persons identified in a drone frame (loudspeaker-style messages).",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Drone ID (1-4)"},
                    "frame_num": {"type": "integer", "description": "Frame number"},
                    "additional_context": {"type": "string", "description": "Extra context"},
                },
                "required": ["drone_id", "frame_num"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rescue_operator_suggestions",
            "description": "Generate tactical suggestions for the rescue operator based on a drone frame.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Drone ID (1-4)"},
                    "frame_num": {"type": "integer", "description": "Frame number"},
                    "additional_context": {"type": "string", "description": "Extra context"},
                },
                "required": ["drone_id", "frame_num"],
            },
        },
    },
    #  Drone Controller 
    {
        "type": "function",
        "function": {
            "name": "drone_send_phase1",
            "description": "Send Phase 1 scouting area corners to the drone controller (Unity). Drones will fly to formation and begin scouting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "corners": {
                        "type": "array",
                        "description": "4 corner coordinates [{x, y}, ...] defining the scouting area",
                        "items": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
                    }
                },
                "required": ["corners"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drone_send_phase2",
            "description": "Send Phase 2 sub-zone assignments to drones. Each drone gets a zone to do close-range scouting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phase2_zones": {
                        "type": "array",
                        "description": "4 zone bounds [{minX, maxX, minZ, maxZ}, ...] — one per drone",
                        "items": {
                            "type": "object",
                            "properties": {
                                "minX": {"type": "number"}, "maxX": {"type": "number"},
                                "minZ": {"type": "number"}, "maxZ": {"type": "number"},
                            },
                        },
                    }
                },
                "required": ["phase2_zones"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drone_get_data",
            "description": "Read the drone data log to get GPS positions, altitudes, and battery levels for all drones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Specific drone ID (1-4), or omit for all drones"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drone_get_frame",
            "description": "Get information about a specific drone frame (path, GPS coordinates, timestamp).",
            "parameters": {
                "type": "object",
                "properties": {
                    "drone_id": {"type": "integer", "description": "Drone ID (1-4)"},
                    "frame_num": {"type": "integer", "description": "Frame number"},
                },
                "required": ["drone_id", "frame_num"],
            },
        },
    },
]


#  Tool calls 

async def call_module(method: str, url: str, json_data: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as http:
        if method == "GET":
            resp = await http.get(url)
        else:
            resp = await http.post(url, json=json_data or {})
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
        return resp.json()


def parse_drone_log(drone_id: int = None) -> list[dict]:
    log_path = DATASET_PATH / "drone_data_log.txt"
    entries = []
    with open(log_path, "r") as f:
        lines = f.readlines()
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 6:
            entry = {
                "timestamp": parts[0],
                "drone_id": int(parts[1]),
                "gps_x": float(parts[2]),
                "gps_y": float(parts[3]),
                "altitude": float(parts[4]),
                "battery": float(parts[5]),
            }
            if drone_id is None or entry["drone_id"] == drone_id:
                entries.append(entry)
    return entries


async def execute_tool(name: str, args: dict) -> str:
    try:
        #  Monitor 
        if name == "monitor_scan_trends":
            result = await call_module("POST", f"{MONITOR_URL}/api/monitor/scan_trends")
        elif name == "monitor_analyze_tag":
            result = await call_module("POST", f"{MONITOR_URL}/api/monitor/analyze_tag", {"hashtag": args["hashtag"]})
        elif name == "monitor_update_context":
            result = await call_module("POST", f"{MONITOR_URL}/api/monitor/update_context", {
                "reasoning": args["reasoning"], "source": args.get("source", "agent"),
            })
        elif name == "monitor_get_alerts":
            result = await call_module("GET", f"{MONITOR_URL}/api/monitor/alerts")

        #  Scout 
        elif name == "scout_detect":
            result = await call_module("POST", f"{SCOUT_URL}/api/scout/detect", {
                "drone_id": args["drone_id"], "frame_num": args["frame_num"],
            })
        elif name == "scout_split_zones":
            result = await call_module("POST", f"{SCOUT_URL}/api/scout/split_zones", {
                "grid_size": args.get("grid_size", 4),
            })
        elif name == "scout_danger_rating":
            result = await call_module("POST", f"{SCOUT_URL}/api/scout/danger_rating", {"zone_id": args["zone_id"]})
        elif name == "scout_density":
            result = await call_module("POST", f"{SCOUT_URL}/api/scout/density", {"zone_id": args["zone_id"]})
        elif name == "scout_priority":
            result = await call_module("POST", f"{SCOUT_URL}/api/scout/priority", {"zone_id": args["zone_id"]})
        elif name == "scout_strategy":
            result = await call_module("POST", f"{SCOUT_URL}/api/scout/strategy", {
                "context": args.get("context"),
            })
        elif name == "scout_escape_routes":
            result = await call_module("POST", f"{SCOUT_URL}/api/scout/escape_routes")

        #  Search 
        elif name == "search_update":
            payload = {"drone_id": args["drone_id"], "num_frames": args.get("num_frames", 5)}
            if "start_frame" in args:
                payload["start_frame"] = args["start_frame"]
            result = await call_module("POST", f"{SEARCH_URL}/api/search/update", payload)
        elif name == "search_medical":
            result = await call_module("POST", f"{SEARCH_URL}/api/search/medical", {
                "drone_id": args["drone_id"], "frame_num": args["frame_num"],
            })
        elif name == "search_threats":
            result = await call_module("POST", f"{SEARCH_URL}/api/search/threats", {
                "drone_id": args["drone_id"], "frame_num": args["frame_num"],
            })
        elif name == "search_get_alarms":
            result = await call_module("GET", f"{SEARCH_URL}/api/search/alarms")

        #  Rescue 
        elif name == "rescue_safety_instructions":
            result = await call_module("POST", f"{RESCUE_URL}/api/rescue/safety_instructions", {
                "drone_id": args["drone_id"], "frame_num": args["frame_num"],
                "additional_context": args.get("additional_context"),
            })
        elif name == "rescue_operator_suggestions":
            result = await call_module("POST", f"{RESCUE_URL}/api/rescue/operator_suggestions", {
                "drone_id": args["drone_id"], "frame_num": args["frame_num"],
                "additional_context": args.get("additional_context"),
            })

        #  Drone Controller 
        elif name == "drone_send_phase1":
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(f"{DRONE_CONTROLLER_URL}/start/", json={"corners": args["corners"]})
                result = {"status": resp.status_code, "message": resp.text}
        elif name == "drone_send_phase2":
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(f"{DRONE_CONTROLLER_URL}/start/", json={"phase2_zones": args["phase2_zones"]})
                result = {"status": resp.status_code, "message": resp.text}
        elif name == "drone_get_data":
            drone_id = args.get("drone_id")
            entries = parse_drone_log(drone_id)
            # Return summary
            if entries:
                result = {
                    "total_entries": len(entries),
                    "drones": list(set(e["drone_id"] for e in entries)),
                    "time_range": {"start": entries[0]["timestamp"], "end": entries[-1]["timestamp"]},
                    "first_entry": entries[0],
                    "last_entry": entries[-1],
                    "battery_range": {
                        "min": min(e["battery"] for e in entries),
                        "max": max(e["battery"] for e in entries),
                    },
                }
            else:
                result = {"total_entries": 0, "message": "No data found"}
        elif name == "drone_get_frame":
            drone_id = args["drone_id"]
            frame_num = args["frame_num"]
            frame_path = DATASET_PATH / str(drone_id) / f"frame_{frame_num}.jpg"
            log_path = DATASET_PATH / str(drone_id) / "log.txt"
            gps = None
            if log_path.exists():
                with open(log_path, "r") as f:
                    for line in f.readlines()[1:]:
                        parts = line.strip().split("|")
                        if parts and int(parts[0]) == frame_num:
                            gps = {"x": float(parts[2]), "y": float(parts[3]), "altitude": float(parts[4])}
                            break
            result = {
                "drone_id": drone_id,
                "frame_num": frame_num,
                "frame_exists": frame_path.exists(),
                "frame_path": str(frame_path),
                "gps": gps,
            }
        else:
            result = {"error": f"Unknown tool: {name}"}

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)})


#  Agent chat loop 

SYSTEM_PROMPT = """You are ResQNet Agent, an AI-powered search-and-rescue operations commander.
You have access to tools across 4 operational modules:

**Monitor** — Scan social media for disaster events
**Scout** — Analyze drone footage to assess disaster zones
**Search** — Continuously monitor drone feeds for emergencies and threats
**Rescue** — Generate safety instructions and operator guidance
**Drone Controller** — Send commands to the drone swarm

You should:
1. Use tools proactively to gather information when asked about a situation
2. Chain tools together (e.g., split_zones → danger_rating → priority → strategy)
3. Always explain your reasoning and findings clearly
4. Prioritize human life above all else
5. Flag critical situations with urgency

Current time: {time}
"""


class ChatRequest(BaseModel):
    message: str = Field(description="User message to the agent")
    reset: bool = Field(False, description="Reset conversation history")

class ChatResponse(BaseModel):
    response: str
    tools_used: list[str]
    timestamp: str


@app.post("/api/agent/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest):
    global conversation_history

    if request.reset:
        conversation_history = []

    system_msg = {"role": "system", "content": SYSTEM_PROMPT.format(time=datetime.now(timezone.utc).isoformat())}
    conversation_history.append({"role": "user", "content": request.message})

    messages = [system_msg] + conversation_history
    tools_used = []

    # Agent loop — up to 10 tool calls per turn
    for _ in range(10):
        async with httpx.AsyncClient(timeout=120.0) as http:
            resp = await http.post(
                OPENROUTER_BASE,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": OPENROUTER_LLM_MODEL,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.3,
                },
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"LLM error: {resp.status_code}")
            data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        # If the LLM wants to call tools
        if msg.get("tool_calls"):
            messages.append(msg)
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                logger.info(f"🔧 Tool call: {fn_name}({json.dumps(fn_args)[:100]})")
                tools_used.append(fn_name)

                tool_result = await execute_tool(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
            continue  # Let LLM process tool results

        # Final response — no more tool calls
        final_response = msg.get("content", "")
        conversation_history.append({"role": "assistant", "content": final_response})

        return ChatResponse(
            response=final_response,
            tools_used=tools_used,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Fallback if loop exhausted
    return ChatResponse(
        response="I've reached the maximum number of tool calls for this turn. Please continue with a follow-up question.",
        tools_used=tools_used,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/agent/history")
async def get_history():
    return {"messages": conversation_history}

@app.delete("/api/agent/history")
async def clear_history():
    conversation_history.clear()
    return {"message": "Conversation history cleared"}

@app.get("/api/agent/tools")
async def list_tools():
    return {"total": len(TOOLS), "tools": [t["function"]["name"] for t in TOOLS]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8080)
