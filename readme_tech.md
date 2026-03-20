# ResQNet — Tech Stack Overview

This document outlines the end-to-end technology stack and module architecture for the **ResQNet** platform.

## Architecture Diagram

```mermaid
flowchart TB
    classDef frontend fill:#3b82f6,stroke:#1d4ed8,color:#fff
    classDef agent fill:#10b981,stroke:#047857,color:#fff
    classDef drone fill:#f59e0b,stroke:#b45309,color:#fff
    classDef ai fill:#8b5cf6,stroke:#5b21b6,color:#fff
    classDef external fill:#64748b,stroke:#334155,color:#fff

    subgraph UserInterface ["Web Application"]
        direction TB
        UI["Operator Dashboard"]:::frontend --> Map["Geospatial Maps & Heatmaps"]:::frontend
        UI --> Alarm["Real-time Alarm Panel"]:::frontend
    end

    subgraph ReasoningAgent ["Reasoning Agent (Python / FastAPI)"]
        direction TB
        Agent["Unified Agent Orchestrator"]:::agent --> API["FastAPI Endpoints"]:::agent
        
        API --> Monitor["Phase 0: Monitor<br/>• X/Twitter Scraping (twikit)<br/>• LLM Classification"]:::agent
        
        API --> Scout["Phase 1: Scout<br/>• Zone Mapping & Detections<br/>• Danger/Priority Heatmaps<br/>• Rescue Strategy"]:::agent
        
        API --> Search["Phase 2a: Search<br/>• Continuous Drone Feeds<br/>• Medical & Threat Alarms"]:::agent
        
        API --> Rescue["Phase 2b: Rescue<br/>• Safety Instructions<br/>• Operator Guidance"]:::agent
    end

    subgraph AI_Models ["AI & ML Models"]
        direction TB
        OR["OpenRouter API<br/>• LLMs (Planning & Strategy)<br/>• VLMs (Scene Description)"]:::ai
        YOLO["Ultralytics YOLO<br/>• Local Object Detection<br/>• Building/Person Tracking"]:::ai
    end

    subgraph DroneController ["Drone Controller (Unity / C#)"]
        direction TB
        Sim["Physics & Sensor Simulation<br/>• GPS, Altitude, Battery"]:::drone
        Nav["Flight Stack<br/>• APF Navigation, PID, A*"]:::drone
        Data["Telemetry & Streaming<br/>• WebSocket Feed, Log Saving"]:::drone
        
        Sim --- Nav --- Data
    end

    subgraph External ["External Services"]
        direction TB
        X["X / Twitter Network"]:::external
    end

    %% Data Flow Connections
    UserInterface <-->|REST APIs / WebSockets| ReasoningAgent
    Monitor -->|Scrapes Trends| External
    
    Scout <-->|Dispatch / Drone Logs| DroneController
    Search <-->|Waypoints / Drone Feeds| DroneController
    
    ReasoningAgent <-->|Inference Requests| AI_Models
```

## Technology Stack Breakdown

### 1. Reasoning Agent
* **Language**: Python 3.11+
* **Framework**: FastAPI (Async REST routes), Uvicorn
* **HTTP/Async**: `httpx`, `asyncio`
* **Social Scraping**: `twikit` (Allows unauthenticated Twitter trend and hashtag scraping)
* **Infrastructure**: `pydantic` v2, `loguru` for structured logging, `python-dotenv`

### 2. AI & Machine Learning
* **LLM / VLM API**: OpenRouter unified API
* **Base Models**: `google/gemma-3-4b-it:free` (VLM) & `stepfun/step-3.5-flash:free` (LLM)
* **Local Computer Vision**: Ultralytics YOLOv8/v11 (building detection, people counting, disaster identification)

### 3. Drone Swarm Controller
* **Engine**: Unity 3D Engine (C#)
* **Flight Dynamics**: Custom PID tuning and Artificial Potential Field (APF) logic
* **Pathfinding**: Grid-based local mapping with A*
* **Telemetry Server**: Flask HTTP Server (`received_data_server.py`) on port 8080 for handling drone zip bundles and video stitching (`OpenCV`)

### 4. Web Application (Frontend)
* **Status**: Defining UI Framework
* **Expected Stack**: React, Leaflet/Mapbox for geospatial rendering, WebSockets for live video streaming and alarms.

### 5. Geospatial & Data Tools
* **Mapping**: Expected use of `GeoPandas`, `Folium` for heatmap generation.
* **Image Processing**: `Pillow`, `OpenCV` (cv2) for drone feed pre-processing and video compilation.
