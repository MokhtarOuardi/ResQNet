<script setup>
import { computed } from 'vue'
import { useDroneStore } from '../stores/droneStore'

const droneStore = useDroneStore()

const handleVideoClick = (id) => {
  droneStore.selectDrone(id)
}
</script>

<template>
  <div class="video-grid-container">
    <div 
      v-for="drone in droneStore.drones" 
      :key="drone.id"
      class="video-card"
      :class="{ 
        active: droneStore.selectedDroneId === drone.id,
        offline: drone.status === 'Offline',
        charging: drone.status === 'Charging'
      }"
      @click="handleVideoClick(drone.id)"
    >
      <div class="video-overlay">
        <div class="top-bar">
          <span class="drone-id">{{ drone.id }}</span>
          <span class="battery-status" :class="{ low: drone.battery <= 20 }">
            {{ Math.floor(drone.battery) }}% 🔋
          </span>
        </div>
        
        <div class="bottom-bar">
          <span class="status-badge" :data-status="drone.status">{{ drone.status }}</span>
        </div>
        
        <!-- Crosshair UI for aesthetic -->
        <div class="crosshair ch-tl"></div>
        <div class="crosshair ch-tr"></div>
        <div class="crosshair ch-bl"></div>
        <div class="crosshair ch-br"></div>
      </div>
      
      <div v-if="drone.status === 'Offline' || drone.status === 'Charging'" class="no-signal">
        NO SIGNAL
      </div>
      <img v-else :src="drone.videoSrc" alt="Drone View" class="dashcam-feed" />
    </div>
  </div>
</template>

<style scoped>
.video-grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

/* Custom Scrollbar */
.video-grid-container::-webkit-scrollbar {
  width: 6px;
}
.video-grid-container::-webkit-scrollbar-thumb {
  background: rgba(0, 255, 200, 0.3);
  border-radius: 4px;
}

.video-card {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  aspect-ratio: 16 / 9;
  background: #000;
  border: 1px solid rgba(255, 255, 255, 0.1);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.video-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 20px rgba(0,0,0,0.5), 0 0 15px rgba(0, 255, 200, 0.2);
  border-color: rgba(0, 255, 200, 0.5);
}

.video-card.active {
  border: 2px solid #00ffc8;
  box-shadow: 0 0 20px rgba(0, 255, 200, 0.4);
}

.no-signal {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: repeating-linear-gradient(
    45deg,
    #111,
    #111 10px,
    #222 10px,
    #222 20px
  );
  color: #ff3366;
  font-weight: 800;
  letter-spacing: 4px;
  font-size: 1.2rem;
  z-index: 1;
}

.dashcam-feed {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.8;
  transition: opacity 0.3s;
}

.video-card:hover .dashcam-feed {
  opacity: 1;
}

.video-overlay {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 2;
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: linear-gradient(to bottom, rgba(0,0,0,0.7) 0%, transparent 30%, transparent 70%, rgba(0,0,0,0.7) 100%);
  pointer-events: none;
}

.top-bar, .bottom-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.drone-id {
  font-family: 'Courier New', monospace;
  font-weight: bold;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0,0,0,0.8);
}

.battery-status {
  font-size: 0.85rem;
  color: #00ffc8;
  font-weight: 600;
}

.battery-status.low {
  color: #ff3366;
  animation: blink 1s infinite alternate;
}

@keyframes blink {
  0% { opacity: 1; }
  100% { opacity: 0.4; }
}

.status-badge {
  font-size: 0.75rem;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(4px);
  color: white;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.status-badge[data-status="Exploring"] { color: #00e5ff; border: 1px solid rgba(0, 229, 255, 0.3); }
.status-badge[data-status="Returning"] { color: #ffcc00; border: 1px solid rgba(255, 204, 0, 0.3); }
.status-badge[data-status="Offline"] { color: #ff3366; border: 1px solid rgba(255, 51, 102, 0.3); }
.status-badge[data-status="Charging"] { color: #00ffc8; border: 1px solid rgba(0, 255, 200, 0.3); }
.status-badge[data-status="Assigned"] { color: #b05bff; border: 1px solid rgba(176, 91, 255, 0.3); }

/* Sci-fi crosshairs */
.crosshair {
  position: absolute;
  width: 15px;
  height: 15px;
  border: 2px solid rgba(255,255,255,0.4);
}
.ch-tl { top: 10px; left: 10px; border-right: none; border-bottom: none; }
.ch-tr { top: 10px; right: 10px; border-left: none; border-bottom: none; }
.ch-bl { bottom: 10px; left: 10px; border-right: none; border-top: none; }
.ch-br { bottom: 10px; right: 10px; border-left: none; border-top: none; }

/* Dashcam subtle scanline effect */
.video-overlay::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06));
  background-size: 100% 4px, 6px 100%;
  pointer-events: none;
  z-index: 10;
  opacity: 0.5;
}

.video-overlay::before {
  content: '';
  position: absolute;
  top: -100%; left: 0; right: 0; height: 20%;
  background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(0,255,200,0.2), rgba(255,255,255,0));
  animation: scan 4s linear infinite;
  pointer-events: none;
  z-index: 11;
}

@keyframes scan {
  0% { top: -20%; }
  100% { top: 120%; }
}
</style>
