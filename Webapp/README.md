# 🌐 ResQNet — Swarm Intelligence Dashboard

> **High-fidelity operator interface for the ResQNet drone search-and-rescue platform.**

ResQNet is a specialized drone swarm mission control system designed for high-stakes search-and-rescue (SAR) operations. It provides operators with real-time tactical mapping, drone fleet telemetry, and immersive 3D topography to coordinate rescue efforts in complex environments (fire, flood, etc.).


## ✨ Core Features

### 🗺️ Multi-Mode Tactical Mapping
A proprietary mapping system powered by **OpenLayers** and **CesiumJS**, offering three specialized operational modes:
- **Actual Map**: Standard tactical view with a sci-fi radar aesthetic for real-time fleet positioning.
- **Thermal View**: Heatmap overlays highlighting disaster zones (e.g., fire, flooding) to prioritize rescue paths.
- **3D Topography**: Immersive 3D landscape visualization featuring extruded building data for urban search strategies.

### 🚁 Drone Fleet Management
- **Live Status Monitoring**: Real-time tracking of drone states: `Active`, `Returning`, `Offline`, or `Charging`.
- **Telemetry Analysis**: Instant access to individual drone data, including battery percentage, altitude, velocity, and precise GPS coordinates.
- **Holographic HUD**: Cyberpunk-inspired sidebar for detailed drone telemetry, featuring glassmorphism and subtle micro-animations.

### 🌓 Picture-in-Picture (PiP) Interface
Seamlessly toggle between the global tactical map and live drone camera feeds without losing situational awareness. The PiP window allows operators to maintain focus on mission-critical visuals.

### 🛠️ Integrated Simulation Engine
Built-in drone movement and telemetry simulation for demonstration, training, and testing rescue algorithms without requiring field hardware.

---

## 🛠️ Technical Stack

- **Framework**: [Vue 3](https://vuejs.org/) (Composition API)
- **Build Tool**: [Vite](https://vitejs.dev/)
- **Mapping**: [OpenLayers](https://openlayers.org/) & [Cesium/ol-cesium](https://openlayers.org/ol-cesium/)
- **State Management**: [Pinia](https://pinia.vuejs.org/)
- **Styling**: Vanilla CSS with modern aesthetics (Glassmorphism, HUD overlays)
- **Typography**: Inter / Outfit (Google Fonts)

---

## 🚀 Getting Started

### Prerequisites
- [Node.js](https://nodejs.org/) (v18 or higher)
- npm or yarn

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/MokhtarOuardi/ResQNet.git
   cd Webapp
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Launch the development server:
   ```bash
   npm run dev
   ```

### Production Build
To create a production-optimized build:
```bash
npm run build
```

---

## 📅 Project Status
🏆 **Hackathon 2026 Edition**  
Currently in the functional prototype phase, featuring a working drone simulation and advanced 3D map integration.

---

Part of the **ResQNet** platform.
