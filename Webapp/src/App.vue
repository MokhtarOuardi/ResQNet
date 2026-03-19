<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useDroneStore } from './stores/droneStore'
import MapLayout from './components/MapLayout.vue'
import VideoGrid from './components/VideoGrid.vue'
import DroneDetail from './components/DroneDetail.vue'

const droneStore = useDroneStore()

// 'map' or 'video'
const activeView = ref('map')

const toggleView = () => {
  activeView.value = activeView.value === 'map' ? 'video' : 'map'
}

onMounted(() => {
  droneStore.startSimulation()
})

onUnmounted(() => {
  droneStore.stopSimulation()
})
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="logo">
        <span class="pulse-indicator"></span>
        <h1>FIRST RESPONDER <span class="highlight">SWARM INTELLIGENCE</span></h1>
      </div>
      <div class="fleet-status">
        <div class="status-item">
          <span class="label">ACTIVE DRONES</span>
          <span class="value">{{ droneStore.activeDrones.length }} / {{ droneStore.drones.length }}</span>
        </div>
        <div class="status-item">
          <span class="label">SYSTEM STATUS</span>
          <span class="value ok">NOMINAL</span>
        </div>
      </div>
    </header>
    
    <main class="dashboard-container">
      <!-- Main Fullscreen View -->
      <div class="main-view">
        <transition name="fade" mode="out-in">
          <MapLayout v-if="activeView === 'map'" class="view-component" />
          <VideoGrid v-else class="view-component" />
        </transition>
      </div>
      
      <!-- Overlay HUD Elements -->
      <div class="hud-overlay pointer-events-none">
        <!-- Scanlines effect -->
        <div class="scanlines"></div>
        <div class="vignette"></div>
      </div>

      <!-- Drone Details Sidebar (Holographic Overlay) -->
      <aside class="sidebar-overlay" :class="{ 'is-active': droneStore.selectedDroneId }">
        <DroneDetail />
      </aside>

      <!-- Picture-in-Picture View -->
      <div class="pip-container" @click="toggleView">
        <div class="pip-label">
          <span class="minimize-icon">⤡</span>
          {{ activeView === 'map' ? 'SWITCH TO CAMERAS' : 'SWITCH TO MAP' }}
        </div>
        <div class="pip-content">
          <transition name="fade" mode="out-in">
            <VideoGrid v-if="activeView === 'map'" class="view-component pip-mode" />
            <MapLayout v-else class="view-component pip-mode" />
          </transition>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background-color: #0b0f13;
  color: #fff;
  overflow: hidden;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

.app-header {
  height: 64px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  background: rgba(8, 12, 16, 0.95);
  border-bottom: 1px solid rgba(0, 255, 200, 0.2);
  backdrop-filter: blur(10px);
  z-index: 100;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pulse-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #00ffc8;
  box-shadow: 0 0 10px #00ffc8, 0 0 20px #00ffc8;
  animation: pulse 1.5s infinite alternate;
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1.5); opacity: 0.5; }
}

h1 {
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: 2px;
  margin: 0;
  color: #fff;
}

.highlight {
  color: #00ffc8;
  text-shadow: 0 0 10px rgba(0, 255, 200, 0.5);
}

.fleet-status {
  display: flex;
  gap: 32px;
}

.status-item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.status-item .label {
  font-size: 0.7rem;
  color: rgba(0, 255, 200, 0.6);
  letter-spacing: 1px;
}

.status-item .value {
  font-size: 1.1rem;
  font-weight: 600;
  font-family: monospace;
}

.status-item .value.ok {
  color: #00ffc8;
  text-shadow: 0 0 5px rgba(0, 255, 200, 0.5);
}

.dashboard-container {
  position: relative;
  flex: 1;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.main-view {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 10;
}

.view-component {
  width: 100%;
  height: 100%;
}

.pointer-events-none {
  pointer-events: none;
}

.hud-overlay {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 20;
}

.scanlines {
  width: 100%; height: 100%;
  background: linear-gradient(
    to bottom,
    rgba(255,255,255,0),
    rgba(255,255,255,0) 50%,
    rgba(0,0,0,0.1) 50%,
    rgba(0,0,0,0.1)
  );
  background-size: 100% 4px;
}

.vignette {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  box-shadow: 0 0 150px rgba(0,0,0,0.9) inset;
}

.sidebar-overlay {
  position: absolute;
  top: 24px;
  left: -400px;
  width: 360px;
  height: calc(100% - 48px);
  z-index: 40;
  transition: left 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.sidebar-overlay.is-active {
  left: 24px;
}

.pip-container {
  position: absolute;
  right: 32px;
  bottom: 32px;
  width: 400px;
  height: 250px;
  background: rgba(0,0,0,0.9);
  border: 1px solid rgba(0, 255, 200, 0.4);
  border-radius: 12px;
  z-index: 50;
  cursor: pointer;
  overflow: hidden;
  box-shadow: 0 10px 40px rgba(0,0,0,0.8), 0 0 20px rgba(0, 255, 200, 0.2);
  transition: all 0.3s ease;
}

.pip-container:hover {
  transform: translateY(-5px) scale(1.02);
  box-shadow: 0 15px 50px rgba(0,0,0,0.9), 0 0 30px rgba(0, 255, 200, 0.4);
  border-color: #00ffc8;
}

.pip-label {
  position: absolute;
  top: 0; left: 0; right: 0;
  padding: 6px 12px;
  background: rgba(0, 255, 200, 0.1);
  border-bottom: 1px solid rgba(0, 255, 200, 0.2);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 1px;
  color: #00ffc8;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 2;
  backdrop-filter: blur(4px);
}

.minimize-icon {
  font-size: 1rem;
}

.pip-content {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 1;
}

/* Override components styles when in pip */
:deep(.pip-mode .map-controls) {
  display: none !important;
}

:deep(.pip-mode.video-grid-container) {
  padding-top: 36px !important;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)) !important;
}

:deep(.pip-mode.map-container) {
  border-radius: 0 !important;
  border: none !important;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.4s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
