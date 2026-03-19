<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useDroneStore } from '../stores/droneStore'
import 'ol/ol.css'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import Overlay from 'ol/Overlay'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import Feature from 'ol/Feature'
import GeoJSON from 'ol/format/GeoJSON'
import { Circle as CircleGeom } from 'ol/geom'
import { Style, Fill, Stroke } from 'ol/style'
import { fromLonLat } from 'ol/proj'
import * as Cesium from 'cesium'

import OLCesium from 'ol-cesium'

const droneStore = useDroneStore()
const mapMode = ref('actual') // 'actual', 'heatmap', '3d'
const mapRoot = ref(null)

const modes = [
  { id: 'actual', label: 'Actual Map' },
  { id: 'heatmap', label: 'Thermal View' },
  { id: '3d', label: '3D Topography' }
]

// const BASE_LON = 103.627994 // Taman U
// const BASE_LAT = 1.545442
const BASE_LON = 13.421136 // berlin
const BASE_LAT = 52.540878

const mapXYToLonLat = (x, y) => {
  const lon = BASE_LON + (x - 400) * 0.00005
  const lat = BASE_LAT - (y - 300) * 0.00005
  return [lon, lat]
}

const handleMarkerClick = (id) => {
  droneStore.selectDrone(id)
}

let map = null
let ol3d = null
const droneElements = ref({})
const baseStationEl = ref(null)

// Map-based disaster zones
const disasterZones = [
  { id: 'fire1', type: 'fire', x: 450, y: 250, radius: 150 },
  { id: 'flood1', type: 'flood', x: 300, y: 400, radius: 200 }
]

const disasterSource = new VectorSource()
disasterZones.forEach(zone => {
  const [lon, lat] = mapXYToLonLat(zone.x, zone.y)
  const geom = new CircleGeom(fromLonLat([lon, lat]), zone.radius)
  const feature = new Feature(geom)
  feature.set('type', zone.type)
  disasterSource.addFeature(feature)
})

const disasterLayer = new VectorLayer({
  source: disasterSource,
  style: (feature) => {
    const type = feature.get('type')
    if (type === 'fire') {
      return new Style({
        fill: new Fill({ color: 'rgba(255, 50, 0, 0.4)' }),
        stroke: new Stroke({ color: 'rgba(255, 100, 0, 0.8)', width: 2 })
      })
    } else {
      return new Style({
        fill: new Fill({ color: 'rgba(0, 150, 255, 0.4)' }),
        stroke: new Stroke({ color: 'rgba(0, 200, 255, 0.8)', width: 2 })
      })
    }
  },
  visible: false // Only visible in heatmap mode
})

onMounted(async () => {
  try {
    map = new Map({
      target: mapRoot.value,
      layers: [
        new TileLayer({
          source: new OSM(),
          className: 'ol-layer-custom-dark'
        }),
        disasterLayer
      ],
      view: new View({
        center: fromLonLat([BASE_LON, BASE_LAT]),
        zoom: 16
      }),
    controls: []
    })

    // Initialize OLCesium statically 
    const OLCesiumConstructor = OLCesium.default || OLCesium
    ol3d = new OLCesiumConstructor({ map: map })
    const scene = ol3d.getCesiumScene()

    // Preload Cesium assets statically to prevent delay on first UI toggle
    ol3d.setEnabled(true)
    ol3d.setEnabled(false)

    // Prepare 3D Buildings Vector Layer from GeoJSON
    const buildingsSource = new VectorSource({
      url: '/buildings.geojson',
      format: new GeoJSON()
    })

    const buildingsLayer = new VectorLayer({
      source: buildingsSource,
      style: (feature) => {
        const type = feature.get('type')
        let fillColor = 'rgba(100, 150, 200, 0.4)' // Default for unidentified types

        if (type === 'residential') fillColor = 'rgba(80, 180, 255, 0.5)'
        if (type === 'commercial') fillColor = 'rgba(255, 180, 80, 0.5)'
        if (type === 'education') fillColor = 'rgba(180, 80, 255, 0.5)'

        // Fallback for explicit fillColor in properties
        const customFillColor = feature.get('fillColor')
        if (customFillColor) fillColor = customFillColor

        const strokeColor = feature.get('strokeColor') || '#00ffc8'
        return new Style({
          fill: new Fill({ color: fillColor }),
          stroke: new Stroke({ color: strokeColor, width: 1 })
        })
      },
      visible: true
    })

    buildingsLayer.set('olcs_shadows', true)
    buildingsLayer.set('olcs_extrudedProperty', 'olcs_extruded_height')
    map.addLayer(buildingsLayer)

    // Configure OLCesium Lighting
    scene.shadowMap.enabled = true
    scene.globe.enableLighting = true

    // Building Highlight Selection Logic
    const selectionStyle = new Style({
      fill: new Fill({ color: [0, 255, 200, 1] }),
      stroke: new Stroke({ color: '#ffffff', width: 3 })
    })

    let selectedFeature
    map.on('click', (e) => {
      if (selectedFeature) {
        selectedFeature.setStyle(null)
      }
      selectedFeature = map.forEachFeatureAtPixel(
        e.pixel,
        (feature, layer) => (layer === buildingsLayer ? feature : undefined)
      )
      if (selectedFeature) {
        selectedFeature.setStyle(selectionStyle)
      }
    })

    // Continuous DOM Project Loop
    let rafId
    const syncDOM = () => {
      if (!map) return;

      const projectDOM = (el, lon, lat) => {
        if (!el) return
        let px = null
        if (ol3d && ol3d.getEnabled()) {
          const cartesian = Cesium.Cartesian3.fromDegrees(lon, lat)
          const windowPos = scene.cartesianToCanvasCoordinates(cartesian)
          if (windowPos) px = [windowPos.x, windowPos.y]
        } else {
          px = map.getPixelFromCoordinate(fromLonLat([lon, lat]))
        }
        if (px) {
          el.style.transform = `translate(calc(${px[0]}px - 50%), calc(${px[1]}px - 50%))`
          el.style.display = 'block'
        } else {
          el.style.display = 'none'
        }
      }

      // Sync Base Station
      projectDOM(baseStationEl.value, BASE_LON, BASE_LAT)

      // Sync Drones
      droneStore.drones.forEach(drone => {
        const el = droneElements.value[drone.id]
        if (!el) return
        const [lon, lat] = mapXYToLonLat(drone.position.x, drone.position.y)
        projectDOM(el, lon, lat)
      })

      rafId = requestAnimationFrame(syncDOM)
    }
    
    syncDOM()

    onUnmounted(() => {
      cancelAnimationFrame(rafId)
      if (ol3d) ol3d.setEnabled(false)
      if (map) map.setTarget(null)
    })
  } catch (err) {
    document.body.innerHTML += `<div style="position:absolute;z-index:99999;background:red;color:white;padding:20px;font-size:24px;top:0;left:0">${err.message}<br><pre>${err.stack}</pre></div>`;
    throw err;
  }
})

watch(mapMode, (newMode) => {
  if (!map || !ol3d) return
  
  if (newMode === '3d') {
    ol3d.setEnabled(true)
    disasterLayer.setVisible(false)
  } else {
    ol3d.setEnabled(false)
    disasterLayer.setVisible(newMode === 'heatmap')
  }
})
</script>

<template>
  <div class="map-container" :class="[`mode-${mapMode}`]">
    <!-- Mode Controls -->
    <div class="map-controls">
      <button 
        v-for="mode in modes" 
        :key="mode.id" 
        class="control-btn"
        :class="{ active: mapMode === mode.id }"
        @click.stop="mapMode = mode.id"
      >
        {{ mode.label }}
      </button>
    </div>

    <!-- The Map Viewport -->
    <div class="map-viewport">
      <div class="map-grid" ref="mapRoot">
        <!-- Radar Sweep in Tactical Mode -->
        <div class="radar-sweep" v-if="mapMode === 'actual'"></div>
      </div>
    </div>

    <!-- Floating Overlays -->
    <div class="floating-overlays">
      <div ref="baseStationEl" class="base-station">
        <div class="base-ring"></div>
        <span class="icon">⌂</span>
      </div>

      <div 
        v-for="drone in droneStore.drones" 
        :key="drone.id"
        :ref="el => { if(el) droneElements[drone.id] = el }"
        class="drone-marker"
        :class="{ active: droneStore.selectedDroneId === drone.id, offline: drone.status === 'Offline', returning: drone.status === 'Returning' }"
        @click.stop="handleMarkerClick(drone.id)"
      >
        <div class="marker-pulse" v-if="drone.status !== 'Offline' && drone.status !== 'Charging'"></div>
        <div class="marker-core"></div>
        <div class="marker-label">{{ drone.id }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.map-container {
  width: 100%;
  height: 100%;
  position: relative;
  background: #05080a;
  overflow: hidden;
  border-radius: 16px;
}

.map-controls {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 100;
  display: flex;
  gap: 8px;
  background: rgba(0,0,0,0.6);
  padding: 6px;
  border-radius: 8px;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(0, 255, 200, 0.2);
}

.control-btn {
  background: transparent;
  border: 1px solid transparent;
  color: rgba(255,255,255,0.6);
  padding: 6px 12px;
  font-family: 'Inter', monospace;
  font-size: 0.75rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
}

.control-btn:hover {
  color: #fff;
  background: rgba(255,255,255,0.05);
}

.control-btn.active {
  background: rgba(0, 255, 200, 0.15);
  border-color: #00ffc8;
  color: #00ffc8;
  box-shadow: 0 0 10px rgba(0, 255, 200, 0.3);
}

.map-viewport {
  width: 100%;
  height: 100%;
  position: relative;
}

.map-grid {
  width: 100%;
  height: 100%;
  position: relative;
}

/* Invert OpenStreetMap colors to create a dark sci-fi radar map */
:deep(.ol-layer-custom-dark) {
  filter: invert(100%) hue-rotate(180deg) brightness(85%) contrast(1.2) sepia(60%) saturate(150%) hue-rotate(130deg);
}

/* Prevent css filters applying double in Cesium mode or messing with the Cesium widget */
:deep(.cesium-viewer) {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
}

.radar-sweep {
  position: absolute;
  top: 50%; left: 50%;
  width: 200%; height: 200%;
  background: conic-gradient(from 0deg, transparent 70%, rgba(0, 255, 200, 0.15) 100%);
  border-radius: 50%;
  transform-origin: center;
  margin-top: -100%; margin-left: -100%;
  animation: radar-spin 4s linear infinite;
  pointer-events: none;
  z-index: 5;
}

@keyframes radar-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* Overlays Container */
.floating-overlays {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  pointer-events: none;
  z-index: 10;
}
.floating-overlays > * {
  position: absolute;
  top: 0; left: 0;
  pointer-events: auto;
}

/* Markers */
.base-station {
  display: block;
  color: #00ffc8;
}
.base-ring {
  position: absolute;
  width: 40px; height: 40px;
  border: 2px dashed rgba(0, 255, 200, 0.5);
  border-radius: 50%;
  top: -20px; left: -10px;
  animation: spin 10s linear infinite;
}

.drone-marker {
  width: 14px;
  height: 14px;
  cursor: pointer;
  transition: transform 0.5s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.marker-core {
  width: 100%;
  height: 100%;
  background-color: #00ffc8;
  border-radius: 50%;
  box-shadow: 0 0 10px #00ffc8, 0 0 20px #00ffc8;
  position: relative;
  z-index: 2;
}

.drone-marker.active .marker-core { background-color: #fff; box-shadow: 0 0 15px #fff, 0 0 30px #fff; }
.drone-marker.offline .marker-core { background-color: #ff3366; box-shadow: 0 0 10px #ff3366; }
.drone-marker.returning .marker-core { background-color: #ffcc00; box-shadow: 0 0 10px #ffcc00; }

.marker-pulse {
  position: absolute;
  top: -50%; left: -50%; width: 200%; height: 200%;
  border-radius: 50%; border: 1px solid #00ffc8;
  animation: pulse 2s infinite ease-out;
  opacity: 0;
}
.drone-marker.returning .marker-pulse { border-color: #ffcc00; }

@keyframes pulse {
  0% { transform: scale(0.5); opacity: 1; }
  100% { transform: scale(2.5); opacity: 0; }
}

@keyframes spin { 100% { transform: rotate(360deg); } }

.marker-label {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  font-weight: bold;
  color: #fff;
  text-shadow: 0 2px 4px #000;
  white-space: nowrap;
  font-family: 'Inter', monospace;
  pointer-events: none;
  background: rgba(0,0,0,0.5);
  padding: 2px 4px;
  border-radius: 4px;
}
</style>
