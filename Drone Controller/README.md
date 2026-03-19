# 🎮 ResQNet — Drone Controller

> **Drone swarm coordination and flight control module for the ResQNet platform.**

The Drone Controller manages real-time communication with the drone swarm, handling flight path coordination, telemetry collection, and mission-critical waypoint management. Built in Unity, it simulates high-fidelity drone physics and sensor data for testing AI-driven search and rescue operations.

---

## 🏗️ System Architecture

The module is built on a layered architecture that bridges high-level mission planning with low-level flight stabilization.

- **Mission Orchestration**: `Scouting_Phase_1` acts as the mission commander, processing bounds from the Reasoning Agent and delegating tasks to the swarm.
- **Swarm Intelligence**: `Swarm_Drone_Organizer` manages formations and relative offsets, allowing the swarm to move as a unified entity.
- **Flight Stack**: `droneMovementController` combines PID stabilization with Artificial Potential Field (APF) logic for smooth, collision-free flight.
- **Environmental Awareness**: `Scouting_Grid_Mapper` builds dynamic occupancy and height maps using raycasts, powering local A* pathfinding.
- **Data Pipeline**: Telemetry and video feeds are published via WebSockets (`Publish_Cameras`) and logged locally for post-mission analysis (`Save_Videos_Store`).

---

## 🚁 Mission Workflow

The system operates in two distinct phases to maximize search efficiency:

### 📡 Phase 1: Scout (Lane Sweep)
- **Objective**: High-altitude (20m) wide-area mapping.
- **Pattern**: Serpantine lane sweep covering the entire mission area.
- **Outcome**: Generates a base terrain map and identifies potential target zones for closer inspection.

### 🔍 Phase 2: Search (Quadrant Sweep)
- **Objective**: Low-altitude (8m) detailed inspection.
- **Pattern**: High-resolution quadrant sweeps in areas flagged by the Reasoning Agent.
- **Outcome**: Captures high-detail JPG sequences for object detection and visual confirmation.

---

## ✨ Key Features

- **Autonomous Collision Avoidance**: Real-time APF-based repulsion from obstacles and other drones.
- **Adaptive Pathfinding**: Dynamic A* navigation with automated altitude smoothing to prevent ground collisions.
- **Swarm Formations**: Switch between Square, Diamond, and Line formations on the fly.
- **Live Video Streaming**: Real-time JPG-over-WebSocket streaming for remote monitoring.
- **Sensor Emulation**: High-fidelity simulation of GPS (with noise), Barometer, Gyro, Magnetometer, and Battery drain.

---

## 🛠️ Setup & Controls

### Quick Start
1. Open the Unity project and locate the `Drone_Controller` prefab.
2. In the `Scouting_Phase_1` component, define the 4 area corners in the Inspector (or let the Reasoning Agent provide them via HTTP).
3. Ensure the `received_data_server.py` is running to receive telemetry and video data.
4. Press `Play` in Unity.

### Keyboard Controls
- `S`: **Start Mission** / Advance to Next Phase.
- `R`: **Toggle Recording** (Telemetry & Video).
- `T`: **Toggle Top-Down View** (Cinematic Camera).
- `C`: **Cycle Camera Viewpoints**.
- `Keypad 4/6/8/2`: Manual Camera Positioning.

---

## 📜 Scripts Overview

The following Unity C# scripts power the drone's flight, sensors, and mission logic.

### Core Flight Control
- **[droneMovementController.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/droneMovementController.cs)**: The central flight brain. Manages PID-based stabilization and implements APF for obstacle avoidance.
- **[PID.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/PID.cs)**: A robust controller implementation with integral clamping to prevent oscillation.
- **[droneSettings.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/droneSettings.cs)**: Centralized configuration for PID constants, flight limits, and utilities.
- **[rotor.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/rotor.cs)**: Simulates physical rotor thrust and visual rotation animation.

### Mission & Swarm Coordination
- **[Scouting_Phase_1.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Scouting_Phase_1.cs)**: The mission orchestrator. Manages mission states and coordinates with the Reasoning Agent.
- **[Swarm_Drone_Organizer.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Swarm_Drone_Organizer.cs)**: Handles swarm formations and manages relative offsets.
- **[Scouting_Grid_Mapper.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Scouting_Grid_Mapper.cs)**: Builds real-time terrain maps and provides A* pathfinding.

### Sensor Simulation
- **[GPS.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/GPS.cs)**: Provides noisy geolocation coordinates (X, Z).
- **[Barometer.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Barometer.cs)**: Simulates altitude and vertical speed measurements.
- **[Gyro.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Gyro.cs)**: Calculates pitch and roll based on drone physics.
- **[Magnetometer.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Magnetometer.cs)**: Determines heading (Yaw) relative to a virtual north pole.
- **[Accelerometer.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Accelerometer.cs)**: Measures local linear velocity and acceleration.
- **[Battery.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Battery.cs)**: Tracks power consumption and remaining capacity.

### Data & Communication
- **[Publish_Cameras.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Publish_Cameras.cs)**: Streams live camera feeds via WebSockets.
- **[Save_Videos_Store.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/Save_Videos_Store.cs)**: Records telemetry logs and saves camera frames as JPG sequences.
- **[UnityMainThreadDispatcher.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/UnityMainThreadDispatcher.cs)**: Ensures thread-safe execution of Unity API calls.

### Camera & Visuals
- **[cameraBehaviour.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/cameraBehaviour.cs)**: Cinematic follower camera designed for swarm visualization.
- **[lookAt.cs](file:///d:/Programming_Projects/ResQNet/Drone%20Controller/lookAt.cs)**: Simple target-tracking utility with switchable viewpoints.

---

Part of the **ResQNet** platform — Hackathon 2025.
