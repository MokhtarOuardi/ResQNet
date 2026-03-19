<script setup>
import { computed } from 'vue'
import { useDroneStore } from '../stores/droneStore'

const droneStore = useDroneStore()

const drone = computed(() => droneStore.selectedDrone)

const closeDetail = () => {
  droneStore.selectDrone(null)
}
</script>

<template>
  <div class="detail-sidebar" v-if="drone">
    <div class="header">
      <h2>{{ drone.name }} <span class="badge">{{ drone.id }}</span></h2>
      <button class="close-btn" @click="closeDetail">×</button>
    </div>
    
    <div class="status-panel">
      <div class="metric-group">
        <label>Current Status</label>
        <div class="metric-value status" :data-status="drone.status">{{ drone.status }}</div>
      </div>
      
      <div class="metric-group">
        <label>Assigned Mission</label>
        <div class="metric-value code-font">{{ drone.mission }}</div>
      </div>
      
      <div class="metric-row">
        <div class="metric-group">
          <label>Position X</label>
          <div class="metric-value coord">{{ Math.round(drone.position.x) }}</div>
        </div>
        <div class="metric-group">
          <label>Position Y</label>
          <div class="metric-value coord">{{ Math.round(drone.position.y) }}</div>
        </div>
      </div>
      
      <div class="metric-group">
        <label>Power Core</label>
        <div class="battery-bar-container">
          <div 
            class="battery-bar" 
            :style="{ width: `${drone.battery}%` }"
            :class="{ low: drone.battery <= 20, charging: drone.status === 'Charging' }"
          ></div>
        </div>
        <div class="battery-label">{{ Math.floor(drone.battery) }}%</div>
      </div>

      <div class="diagnostics">
        <label>System Diagnostics Logs</label>
        <div class="console-box">
          <p>[SYS] Connection established.</p>
          <p>[SYS] Telemetry stream active.</p>
          <p v-if="drone.status === 'Exploring'">[NAV] Search pattern engaged.</p>
          <p v-if="drone.status === 'Returning'">[WARN] Triggering return-to-base protocol.</p>
          <p v-if="drone.battery < 30">[WARN] Battery level critical.</p>
        </div>
      </div>
    </div>
  </div>
  <div class="detail-sidebar empty" v-else>
    <div class="empty-state">
      <div class="icon">⌖</div>
      <p>Select a drone from the map or video grid to view detailed telemetry</p>
    </div>
  </div>
</template>

<style scoped>
.detail-sidebar {
  width: 100%;
  height: 100%;
  background: rgba(14, 18, 22, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 16px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  backdrop-filter: blur(20px);
  box-shadow: -10px 0 30px rgba(0,0,0,0.5);
  transition: all 0.3s ease;
}

.detail-sidebar.empty {
  justify-content: center;
  align-items: center;
  opacity: 0.6;
}

.empty-state {
  text-align: center;
  color: rgba(255,255,255,0.4);
  max-width: 80%;
}

.empty-state .icon {
  font-size: 48px;
  margin-bottom: 16px;
  color: rgba(0, 255, 200, 0.2);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 16px;
}

h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 12px;
}

.badge {
  font-size: 0.75rem;
  background: rgba(0, 255, 200, 0.15);
  color: #00ffc8;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid rgba(0, 255, 200, 0.3);
  font-family: monospace;
}

.close-btn {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.5);
  font-size: 24px;
  cursor: pointer;
  transition: color 0.2s;
}

.close-btn:hover {
  color: #ff3366;
}

.status-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.metric-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-row {
  display: flex;
  gap: 16px;
}
.metric-row .metric-group {
  flex: 1;
}

label {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: rgba(255, 255, 255, 0.4);
  font-weight: 600;
}

.metric-value {
  font-size: 1.1rem;
  color: #fff;
  background: rgba(0, 0, 0, 0.4);
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.metric-value.code-font, .metric-value.coord {
  font-family: 'Courier New', Courier, monospace;
}

.metric-value.status[data-status="Exploring"] { color: #00e5ff; border-color: rgba(0, 229, 255, 0.3); box-shadow: 0 0 10px rgba(0, 229, 255, 0.1); }
.metric-value.status[data-status="Returning"] { color: #ffcc00; border-color: rgba(255, 204, 0, 0.3); box-shadow: 0 0 10px rgba(255, 204, 0, 0.1); }
.metric-value.status[data-status="Offline"] { color: #ff3366; border-color: rgba(255, 51, 102, 0.3); }

.battery-bar-container {
  height: 8px;
  background: rgba(255,255,255,0.1);
  border-radius: 4px;
  overflow: hidden;
  margin-top: 4px;
}

.battery-bar {
  height: 100%;
  background: #00ffc8;
  border-radius: 4px;
  transition: width 0.3s ease, background-color 0.3s ease;
}

.battery-bar.low {
  background: #ff3366;
}

.battery-bar.charging {
  background: #00e5ff;
  animation: pulse-charge 1.5s infinite;
}

@keyframes pulse-charge {
  0% { opacity: 0.6; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
}

.battery-label {
  font-size: 0.8rem;
  text-align: right;
  color: rgba(255,255,255,0.7);
  margin-top: 4px;
}

.diagnostics {
  margin-top: 8px;
}

.console-box {
  background: #05080a;
  border: 1px solid #1a2228;
  border-radius: 8px;
  padding: 12px;
  font-family: monospace;
  font-size: 0.8rem;
  color: #00ffc8;
  height: 120px;
  overflow-y: auto;
  box-shadow: inset 0 0 10px rgba(0,0,0,0.8);
}

.console-box p {
  margin: 0 0 4px 0;
  opacity: 0.8;
}

.console-box p:last-child {
  opacity: 1;
}

</style>
