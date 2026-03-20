import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from twikit import Client as TwitterClient
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from loguru import logger

# Config
load_dotenv()

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "")
TWITTER_EMAIL = os.getenv("TWITTER_EMAIL", "")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_VLM_MODEL = os.getenv("OPENROUTER_VLM_MODEL", "google/gemma-3-4b-it:free")
OPENROUTER_LLM_MODEL = os.getenv("OPENROUTER_LLM_MODEL", "stepfun/step-3.5-flash:free")
OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"

COOKIES_PATH = Path(__file__).parent / "cookies.json"

# FastAPI App
app = FastAPI(
    title="ResQNet Monitor",
    description="",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory state
reasoning_context: list[dict] = []
latest_scan: dict = {
    "last_run": None,
    "alerts": [],
}
_twitter_client: Optional[TwitterClient] = None

# twikit
async def get_twitter_client() -> TwitterClient:
    global _twitter_client

    if _twitter_client is not None:
        return _twitter_client

    client = TwitterClient("en-US")

    if COOKIES_PATH.exists():
        try:
            client.load_cookies(str(COOKIES_PATH))
            logger.info("Loaded Twitter cookies from file")
            _twitter_client = client
            return client
        except Exception as e:
            logger.warning(f"Could not load cookies: {e}")

    if not all([TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD]):
        raise HTTPException(
            status_code=500,
            detail="Twitter credentials not configured. Set TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD in .env",
        )

    try:
        await client.login(
            auth_info_1=TWITTER_USERNAME,
            auth_info_2=TWITTER_EMAIL,
            password=TWITTER_PASSWORD,
        )
        client.save_cookies(str(COOKIES_PATH))
        logger.info("Logged in to Twitter and saved cookies")
        _twitter_client = client
        return client
    except Exception as e:
        logger.error(f"Twitter login failed: {e}")
        raise HTTPException(status_code=500, detail=f"Twitter login failed: {e}")

#  LLM 
async def llm_chat(messages: list[dict], temperature: float = 0.3) -> str:
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY not configured in .env",
        )

    async with httpx.AsyncClient(timeout=60.0) as http:
        resp = await http.post(
            OPENROUTER_BASE,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_LLM_MODEL,
                "messages": messages,
                "temperature": temperature,
            },
        )

        if resp.status_code != 200:
            logger.error(f"OpenRouter error {resp.status_code}: {resp.text}")
            raise HTTPException(
                status_code=502,
                detail=f"LLM request failed: {resp.status_code}",
            )

        data = resp.json()
        return data["choices"][0]["message"]["content"]


class TrendAlert(BaseModel):
    hashtag: str
    status: str = Field(description="'disaster' or 'not_relevant'")
    reasoning: str = Field(description="LLM reasoning for classification")
    disaster_type: Optional[str] = Field(None, description="flood, fire, earthquake, etc.")
    confidence: float = Field(description="0.0 to 1.0")

class ScanTrendsResponse(BaseModel):
    timestamp: str
    trends_checked: int
    alerts: list[TrendAlert]

class AnalyzeTagRequest(BaseModel):
    hashtag: str = Field(description="Hashtag to deep-dive (with or without #)")

class AnalyzeTagResponse(BaseModel):
    hashtag: str
    tweets_analyzed: int
    summary: str = Field(description="LLM summary of rescue-relevant information")
    reasoning: str = Field(description="LLM detailed reasoning")
    incident_details: dict = Field(description="Extracted details: location, severity, type, etc.")

class UpdateContextRequest(BaseModel):
    reasoning: str = Field(description="New LLM reasoning to append to the running context")
    source: str = Field("manual", description="Source label: 'scan_trends', 'analyze_tag', 'manual'")

class UpdateContextResponse(BaseModel):
    context_length: int
    total_entries: int
    message: str


# F1
@app.post("/api/monitor/scan_trends", response_model=ScanTrendsResponse)
async def scan_trends():

    logger.info("Starting trend scan...")

    # scrape trending topics from Twitter
    client = await get_twitter_client()

    try:
        trending = await client.get_trends("trending")
        trend_names = []
        for trend in trending[:30]:  # top 30 trends
            name = getattr(trend, "name", None) or str(trend)
            trend_names.append(name)
        logger.info(f"Fetched {len(trend_names)} trending topics")
    except Exception as e:
        logger.error(f"Failed to fetch trends: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch trends: {e}")

    # Send to LLM
    prompt = f"""You are a disaster-monitoring AI for a search-and-rescue platform called ResQNet.

Analyze the following trending topics from X (Twitter) and identify ANY that could be related to:
- Natural disasters (earthquake, flood, hurricane, typhoon, tornado, wildfire, tsunami, landslide)
- Man-made disasters (explosion, building collapse, industrial accident, mass casualty event)
- Emergency situations requiring search and rescue

Trending topics:
{json.dumps(trend_names, indent=2)}

For EACH trend, respond with a JSON array. Only include trends that ARE disaster-related.
If none are disaster-related, return an empty array [].

Each object must have:
- "hashtag": the trending topic name
- "status": "disaster"
- "reasoning": why you believe this is disaster-related (2-3 sentences)
- "disaster_type": type of disaster (e.g. "flood", "earthquake", "fire", "hurricane", etc.)
- "confidence": 0.0 to 1.0 confidence score

Respond with ONLY valid JSON array, no markdown formatting, no code blocks."""

    llm_response = await llm_chat([
        {"role": "system", "content": "You are a disaster classification expert. Respond only with valid JSON."},
        {"role": "user", "content": prompt},
    ])
    try:
        cleaned = llm_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        alerts = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"LLM returned non-JSON: {llm_response[:200]}")
        alerts = []

    alert_objects = [TrendAlert(**a) for a in alerts]

    result = ScanTrendsResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        trends_checked=len(trend_names),
        alerts=alert_objects,
    )

    latest_scan["last_run"] = result.timestamp
    latest_scan["alerts"] = [a.model_dump() for a in alert_objects]

    if alert_objects:
        context_entry = {
            "timestamp": result.timestamp,
            "source": "scan_trends",
            "summary": f"Detected {len(alert_objects)} potential disaster(s): "
                       + ", ".join(a.hashtag for a in alert_objects),
            "alerts": [a.model_dump() for a in alert_objects],
        }
        reasoning_context.append(context_entry)
        logger.info(f"Added {len(alert_objects)} alerts to reasoning context")

    logger.info(f"Trend scan complete. {len(alert_objects)} alerts detected.")
    return result


# F2
@app.post("/api/monitor/analyze_tag", response_model=AnalyzeTagResponse)
async def analyze_hashtag(request: AnalyzeTagRequest):
    hashtag = request.hashtag.lstrip("#")
    logger.info(f"Analyzing hashtag: #{hashtag}")

    # Search tweets with this hashtag
    client = await get_twitter_client()

    try:
        search_results = await client.search_tweet(f"#{hashtag}", product="Latest", count=20)
        tweets_text = []
        for tweet in search_results:
            text = getattr(tweet, "text", None) or str(tweet)
            user = getattr(tweet, "user", None)
            username = getattr(user, "screen_name", "unknown") if user else "unknown"
            created = getattr(tweet, "created_at", "")
            tweets_text.append({
                "user": username,
                "text": text,
                "time": str(created),
            })
        logger.info(f"Fetched {len(tweets_text)} tweets for #{hashtag}")
    except Exception as e:
        logger.error(f"Failed to search tweets: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to search tweets: {e}")

    # Build context
    context_summary = ""
    if reasoning_context:
        recent = reasoning_context[-3:]
        context_summary = "\n\nPrevious monitoring context:\n" + json.dumps(recent, indent=2)

    # Send to LLM
    prompt = f"""You are an intelligence analyst for ResQNet, a search-and-rescue platform.

Analyze the following tweets from the hashtag #{hashtag} and extract ALL information relevant to a rescue team responding to an incident.
{context_summary}

Tweets from #{hashtag}:
{json.dumps(tweets_text, indent=2)}

Provide your response as a JSON object with these fields:
- "summary": A concise 2-4 sentence summary of the situation for rescue commanders
- "reasoning": Your detailed analysis (what you know, what you inferred, what's uncertain)
- "incident_details": an object with:
  - "disaster_type": type of disaster/incident
  - "location": best known location (city, region, coordinates if mentioned)
  - "severity": "low", "medium", "high", or "critical"
  - "estimated_affected": estimated number of people affected (or "unknown")
  - "hazards": list of identified hazards (e.g. ["flooding", "power outage", "road blockage"])
  - "resources_needed": list of resources likely needed (e.g. ["boats", "helicopters", "medical teams"])
  - "timeline": when the incident started (if known)
  - "key_updates": list of the most important individual updates from tweets

Respond with ONLY valid JSON, no markdown formatting, no code blocks."""

    llm_response = await llm_chat([
        {"role": "system", "content": "You are a disaster intelligence analyst. Respond only with valid JSON."},
        {"role": "user", "content": prompt},
    ])

    try:
        cleaned = llm_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        analysis = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"LLM returned non-JSON: {llm_response[:200]}")
        analysis = {
            "summary": llm_response[:500],
            "reasoning": "Failed to parse structured response",
            "incident_details": {},
        }

    result = AnalyzeTagResponse(
        hashtag=f"#{hashtag}",
        tweets_analyzed=len(tweets_text),
        summary=analysis.get("summary", ""),
        reasoning=analysis.get("reasoning", ""),
        incident_details=analysis.get("incident_details", {}),
    )

    context_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "analyze_tag",
        "hashtag": f"#{hashtag}",
        "summary": result.summary,
        "incident_details": result.incident_details,
    }
    reasoning_context.append(context_entry)
    logger.info(f"Hashtag analysis complete. Added to reasoning context.")

    return result


# F3
@app.post("/api/monitor/update_context", response_model=UpdateContextResponse)
async def update_context(request: UpdateContextRequest):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": request.source,
        "reasoning": request.reasoning,
    }
    reasoning_context.append(entry)

    logger.info(f"Context updated. Total entries: {len(reasoning_context)}")

    return UpdateContextResponse(
        context_length=sum(len(json.dumps(e)) for e in reasoning_context),
        total_entries=len(reasoning_context),
        message=f"Context updated successfully. {len(reasoning_context)} entries in history.",
    )


# api

@app.get("/api/monitor/status")
async def get_status():
    """Get the latest monitoring status and cached alerts."""
    return {
        "status": "active",
        "last_run": latest_scan["last_run"],
        "alert_count": len(latest_scan["alerts"]),
        "context_entries": len(reasoning_context),
    }


@app.get("/api/monitor/alerts")
async def get_alerts():
    """Get the latest disaster alerts from the most recent scan."""
    return {
        "last_run": latest_scan["last_run"],
        "alerts": latest_scan["alerts"],
    }


@app.get("/api/monitor/context")
async def get_context():
    """Get the full reasoning context history."""
    return {
        "total_entries": len(reasoning_context),
        "context": reasoning_context,
    }


@app.delete("/api/monitor/context")
async def clear_context():
    """Clear the reasoning context history."""
    reasoning_context.clear()
    return {"message": "Context cleared", "total_entries": 0}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
