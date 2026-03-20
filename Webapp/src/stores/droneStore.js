import { defineStore } from 'pinia'

// Utility function to generate random values between min and max
const rand = (min, max) => Math.floor(Math.random() * (max - min + 1) + min)

export const useDroneStore = defineStore('drone', {
  state: () => ({
    drones: [
      {
        id: 'D-Alpha',
        name: 'Drone Alpha',
        battery: 89,
        status: 'Exploring',
        mission: 'Scan Sector 2',
        position: { x: 200, y: 150 },
        videoSrc: 'https://images.unsplash.com/photo-1508614589041-895b88991e3e?auto=format&fit=crop&q=80&w=600&h=400', // Mock Dashcam View 1 (Mountain terrain)
      },
      {
        id: 'D-Beta',
        name: 'Drone Beta',
        battery: 45,
        status: 'Assigned',
        mission: 'Investigate Thermal Anomaly',
        position: { x: 500, y: 300 },
        videoSrc: 'https://images.unsplash.com/photo-1621532296726-2aeb601bb053?auto=format&fit=crop&q=80&w=600&h=400', // Mock Dashcam View 2 (Forest search)
      },
      {
        id: 'D-Gamma',
        name: 'Drone Gamma',
        battery: 15,
        status: 'Returning',
        mission: 'Low Battery Return',
        position: { x: 350, y: 450 },
        videoSrc: 'https://images.unsplash.com/photo-1542385151-efd9000785a0?auto=format&fit=crop&q=80&w=600&h=400', // Mock Dashcam View 3 (Urban/Rubble search)
      },
      {
        id: 'D-Delta',
        name: 'Drone Delta',
        battery: 100,
        status: 'Charging',
        mission: 'Awaiting deployment',
        position: { x: 50, y: 50 }, // Base station
        videoSrc: 'https://images.unsplash.com/photo-1610484826967-09c5720778c7?auto=format&fit=crop&q=80&w=600&h=400', // Base station overview
      }
    ],
    selectedDroneId: null,
    simulationTimer: null,
  }),
  getters: {
    selectedDrone: (state) => state.drones.find(d => d.id === state.selectedDroneId),
    activeDrones: (state) => state.drones.filter(d => d.status !== 'Charging'),
  },
  actions: {
    selectDrone(id) {
      this.selectedDroneId = id
    },
    // Mock simulation for Live Map & Battery depletion effect
    startSimulation() {
      if (this.simulationTimer) return;
      this.simulationTimer = setInterval(() => {
        this.drones.forEach(drone => {
          if (drone.status === 'Charging') {
            drone.battery = Math.min(100, drone.battery + 2)
            if (drone.battery === 100) {
              drone.status = 'Ready'
              drone.mission = 'Standby'
            }
          } else {
            // Decrease battery
            drone.battery = Math.max(0, drone.battery - 0.5)
            if (drone.battery < 20 && drone.status !== 'Returning') {
              drone.status = 'Returning'
              drone.mission = 'Emergency Return: Low Battery'
            }
            if (drone.battery === 0) {
              drone.status = 'Offline'
              drone.mission = 'Critical Failure'
            }

            // Move exploring or returning drones
            if (drone.status === 'Exploring' || drone.status === 'Assigned') {
              drone.position.x += rand(-5, 5)
              drone.position.y += rand(-5, 5)
            } else if (drone.status === 'Returning') {
              // Move towards base (50, 50)
              const dx = 50 - drone.position.x
              const dy = 50 - drone.position.y
              const dist = Math.sqrt(dx * dx + dy * dy)
              if (dist > 5) {
                drone.position.x += (dx / dist) * 5
                drone.position.y += (dy / dist) * 5
              } else {
                drone.status = 'Charging'
                drone.mission = 'Recharging at Base'
              }
            }
            
            // Constrain to grid
            drone.position.x = Math.max(0, Math.min(800, drone.position.x))
            drone.position.y = Math.max(0, Math.min(600, drone.position.y))
          }
        })
      }, 1000)
    },
    stopSimulation() {
      if (this.simulationTimer) {
        clearInterval(this.simulationTimer)
        this.simulationTimer = null
      }
    }
  }
})
