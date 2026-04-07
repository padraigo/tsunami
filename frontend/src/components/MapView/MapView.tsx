import { useEffect, useRef, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useSimulationStore } from '../../stores/simulationStore'
import { useMapPickStore } from '../../stores/mapPickStore'
import TimelineSlider from './TimelineSlider'

function decodeFrame(base64: string, _rows: number, _cols: number): Float32Array {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new Float32Array(bytes.buffer)
}

function renderFrameToCanvas(
  canvas: HTMLCanvasElement,
  data: Float32Array,
  rows: number,
  cols: number,
  depth?: Float32Array,
): void {
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const imageData = ctx.createImageData(cols, rows)
  // Data is stored row 0 = south (lat_min), but canvas row 0 = top.
  // MapLibre image source maps top-left to [lon_min, lat_max].
  // So we flip vertically: canvas row r reads data row (rows-1-r).
  for (let i = 0; i < data.length; i++) {
    const srcRow = Math.floor(i / cols)
    const srcCol = i % cols
    const flippedRow = rows - 1 - srcRow
    const dataIdx = flippedRow * cols + srcCol
    const v = Math.abs(data[dataIdx])
    const idx = i * 4
    const isLand = depth ? depth[dataIdx] <= 0 : false
    if (isLand || v < 0.01) {
      imageData.data[idx] = 0
      imageData.data[idx + 1] = 0
      imageData.data[idx + 2] = 0
      imageData.data[idx + 3] = 0
    } else if (v < 0.5) {
      const t = v / 0.5
      imageData.data[idx] = 0
      imageData.data[idx + 1] = Math.round(100 + 155 * t)
      imageData.data[idx + 2] = 255
      imageData.data[idx + 3] = Math.round(100 + 155 * t)
    } else if (v < 2) {
      const t = (v - 0.5) / 1.5
      imageData.data[idx] = Math.round(255 * t)
      imageData.data[idx + 1] = 200
      imageData.data[idx + 2] = Math.round(255 * (1 - t))
      imageData.data[idx + 3] = 200
    } else if (v < 5) {
      const t = (v - 2) / 3
      imageData.data[idx] = 255
      imageData.data[idx + 1] = Math.round(200 * (1 - t))
      imageData.data[idx + 2] = 0
      imageData.data[idx + 3] = 220
    } else {
      imageData.data[idx] = 200
      imageData.data[idx + 1] = 0
      imageData.data[idx + 2] = 0
      imageData.data[idx + 3] = 240
    }
  }
  ctx.putImageData(imageData, 0, 0)
}

function renderTideFrameToCanvas(
  canvas: HTMLCanvasElement,
  data: Float32Array,
  rows: number,
  cols: number,
  depth?: Float32Array,
): void {
  // No pre-warping needed — MapLibre's image source handles Mercator projection.
  // We just render equirectangular data and flip vertically (row 0 = south).
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const imageData = ctx.createImageData(cols, rows)
  for (let i = 0; i < cols * rows; i++) {
    const srcRow = Math.floor(i / cols)
    const srcCol = i % cols
    const flippedRow = rows - 1 - srcRow
    const dataIdx = flippedRow * cols + srcCol
    const raw = data[dataIdx]
    const idx = i * 4
    const isLand = depth ? depth[dataIdx] <= 0 : false

    if (isLand || Math.abs(raw) < 0.005) {
      imageData.data[idx] = 0
      imageData.data[idx + 1] = 0
      imageData.data[idx + 2] = 0
      imageData.data[idx + 3] = 0
    } else if (raw < 0) {
      const t = Math.min(1, Math.abs(raw) / 0.5)
      imageData.data[idx] = 30
      imageData.data[idx + 1] = Math.round(100 + 155 * (1 - t))
      imageData.data[idx + 2] = 255
      imageData.data[idx + 3] = Math.round(150 + 100 * t)
    } else {
      const t = Math.min(1, raw / 0.5)
      imageData.data[idx] = 255
      imageData.data[idx + 1] = Math.round(150 * (1 - t))
      imageData.data[idx + 2] = 30
      imageData.data[idx + 3] = Math.round(150 + 100 * t)
    }
  }
  ctx.putImageData(imageData, 0, 0)
}

export default function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const pickMarkerRef = useRef<maplibregl.Marker | null>(null)
  const { current, coarseResult, frames, currentFrameIndex, detailZones, tidalMode } = useSimulationStore()
  const pickPhase = useMapPickStore((s) => s.phase)
  const pickLat = useMapPickStore((s) => s.lat)
  const pickLon = useMapPickStore((s) => s.lon)
  const pickCursorLat = useMapPickStore((s) => s.cursorLat)
  const pickCursorLon = useMapPickStore((s) => s.cursorLon)

  // Init map
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '&copy; OpenStreetMap contributors',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: [140, 10],
      zoom: 2,
    })
    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    mapRef.current = map
    return () => { map.remove(); mapRef.current = null }
  }, [])

  // Map pick click handler
  const handleMapClick = useCallback((e: maplibregl.MapMouseEvent) => {
    const phase = useMapPickStore.getState().phase
    if (phase === 'picking_location') {
      useMapPickStore.getState().setLocation(e.lngLat.lat, e.lngLat.lng)
    } else if (phase === 'picking_direction') {
      useMapPickStore.getState().confirmDirection()
    }
  }, [])

  // Map pick mousemove handler
  const handleMouseMove = useCallback((e: maplibregl.MapMouseEvent) => {
    const phase = useMapPickStore.getState().phase
    if (phase === 'picking_direction') {
      useMapPickStore.getState().updateCursor(e.lngLat.lat, e.lngLat.lng)
    }
  }, [])

  // Register/unregister pick handlers
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    if (pickPhase !== 'idle') {
      map.getCanvas().style.cursor = 'crosshair'
      map.on('click', handleMapClick)
      map.on('mousemove', handleMouseMove)
    } else {
      map.getCanvas().style.cursor = ''
      map.off('click', handleMapClick)
      map.off('mousemove', handleMouseMove)
    }

    return () => {
      map.off('click', handleMapClick)
      map.off('mousemove', handleMouseMove)
      map.getCanvas().style.cursor = ''
    }
  }, [pickPhase, handleMapClick, handleMouseMove])

  // Pick marker (red dot at chosen epicenter)
  useEffect(() => {
    if (pickMarkerRef.current) { pickMarkerRef.current.remove(); pickMarkerRef.current = null }
    const map = mapRef.current
    if (!map || pickLat === null || pickLon === null) return

    const el = document.createElement('div')
    el.className = 'w-5 h-5 bg-red-500 rounded-full border-2 border-white shadow-lg'
    el.style.boxShadow = '0 0 12px rgba(239, 68, 68, 0.7)'
    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([pickLon, pickLat])
      .addTo(map)
    pickMarkerRef.current = marker
  }, [pickLat, pickLon])

  // Arrow line from epicenter to cursor during direction pick
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const updateArrow = () => {
      if (pickPhase !== 'picking_direction' || pickLat === null || pickLon === null || pickCursorLat === null || pickCursorLon === null) {
        // Remove arrow
        if (map.getLayer('pick-arrow-line')) map.removeLayer('pick-arrow-line')
        if (map.getLayer('pick-arrow-head')) map.removeLayer('pick-arrow-head')
        if (map.getSource('pick-arrow')) map.removeSource('pick-arrow')
        return
      }

      const lineData: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: [{
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: [[pickLon, pickLat], [pickCursorLon, pickCursorLat]],
          },
          properties: {},
        }],
      }

      if (map.getSource('pick-arrow')) {
        (map.getSource('pick-arrow') as maplibregl.GeoJSONSource).setData(lineData)
      } else {
        map.addSource('pick-arrow', { type: 'geojson', data: lineData })
        map.addLayer({
          id: 'pick-arrow-line',
          type: 'line',
          source: 'pick-arrow',
          paint: {
            'line-color': '#f59e0b',
            'line-width': 3,
            'line-dasharray': [2, 1],
          },
        })
        map.addLayer({
          id: 'pick-arrow-head',
          type: 'circle',
          source: 'pick-arrow',
          filter: ['==', '$type', 'Point'],
          paint: {
            'circle-radius': 6,
            'circle-color': '#f59e0b',
          },
        })
      }
    }

    if (map.loaded()) updateArrow()
    else map.on('load', updateArrow)
  }, [pickPhase, pickLat, pickLon, pickCursorLat, pickCursorLon])

  // Earthquake marker (for selected simulation)
  useEffect(() => {
    if (!mapRef.current) return
    if (markerRef.current) { markerRef.current.remove(); markerRef.current = null }
    if (!current) return

    const el = document.createElement('div')
    el.className = 'w-4 h-4 bg-red-500 rounded-full border-2 border-white shadow-lg'
    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([current.earthquake_lon, current.earthquake_lat])
      .addTo(mapRef.current)
    markerRef.current = marker

    mapRef.current.flyTo({ center: [current.earthquake_lon, current.earthquake_lat], zoom: 4 })
  }, [current?.uid, current?.earthquake_lat, current?.earthquake_lon])

  // Impact markers
  useEffect(() => {
    const map = mapRef.current
    if (!map || !coarseResult?.impacts?.length) return

    const onLoad = () => {
      const geojsonData: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: coarseResult.impacts.map((imp) => ({
          type: 'Feature' as const,
          geometry: { type: 'Point' as const, coordinates: [imp.lon, imp.lat] },
          properties: { height: imp.max_height },
        })),
      }

      if (map.getSource('impacts')) {
        (map.getSource('impacts') as maplibregl.GeoJSONSource).setData(geojsonData)
      } else {
        map.addSource('impacts', { type: 'geojson', data: geojsonData })
        map.addLayer({
          id: 'impact-circles',
          type: 'circle',
          source: 'impacts',
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['get', 'height'], 0, 3, 5, 12, 10, 20],
            'circle-color': ['interpolate', ['linear'], ['get', 'height'], 0, '#22c55e', 2, '#eab308', 5, '#ef4444', 10, '#7c2d12'],
            'circle-opacity': 0.8,
            'circle-stroke-width': 1,
            'circle-stroke-color': '#fff',
          },
        })
      }
    }

    if (map.loaded()) onLoad()
    else map.on('load', onLoad)
  }, [coarseResult?.impacts])

  // Focus zone rectangles
  useEffect(() => {
    const map = mapRef.current
    if (!map || !current?.focus_zones?.length) return

    const addZones = () => {
      const features: GeoJSON.Feature[] = current.focus_zones.map((z) => ({
        type: 'Feature' as const,
        geometry: {
          type: 'Polygon' as const,
          coordinates: [[
            [z.lon_min, z.lat_min], [z.lon_max, z.lat_min],
            [z.lon_max, z.lat_max], [z.lon_min, z.lat_max],
            [z.lon_min, z.lat_min],
          ]],
        },
        properties: { name: z.name },
      }))

      if (map.getSource('zones')) {
        (map.getSource('zones') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features })
      } else {
        map.addSource('zones', { type: 'geojson', data: { type: 'FeatureCollection', features } })
        map.addLayer({
          id: 'zone-fill',
          type: 'fill',
          source: 'zones',
          paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.15 },
        })
        map.addLayer({
          id: 'zone-outline',
          type: 'line',
          source: 'zones',
          paint: { 'line-color': '#3b82f6', 'line-width': 2 },
        })
      }
    }

    if (map.loaded()) addZones()
    else map.on('load', addZones)
  }, [current?.focus_zones])

  // Inundation extent polygons from detail zones
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const addInundation = () => {
      const features: GeoJSON.Feature[] = []
      for (const zone of detailZones) {
        if (zone.inundation_geojson?.geometry?.coordinates) {
          const geom = zone.inundation_geojson.geometry
          if (geom.type === 'MultiPolygon') {
            for (const poly of geom.coordinates) {
              features.push({
                type: 'Feature',
                geometry: { type: 'Polygon', coordinates: poly },
                properties: { zone_name: zone.zone_name, max_runup_m: zone.max_runup_m },
              })
            }
          } else if (geom.type === 'Polygon' && geom.coordinates.length > 0) {
            features.push({
              type: 'Feature',
              geometry: geom,
              properties: { zone_name: zone.zone_name, max_runup_m: zone.max_runup_m },
            })
          }
        }
      }

      const data: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features }

      if (map.getSource('inundation')) {
        (map.getSource('inundation') as maplibregl.GeoJSONSource).setData(data)
      } else {
        map.addSource('inundation', { type: 'geojson', data })
        map.addLayer({
          id: 'inundation-fill',
          type: 'fill',
          source: 'inundation',
          paint: { 'fill-color': '#dc2626', 'fill-opacity': 0.4 },
        })
        map.addLayer({
          id: 'inundation-outline',
          type: 'line',
          source: 'inundation',
          paint: { 'line-color': '#dc2626', 'line-width': 2 },
        })
      }
    }

    if (map.loaded()) addInundation()
    else map.on('load', addInundation)
  }, [detailZones])

  // Wave animation frame
  useEffect(() => {
    const map = mapRef.current
    if (!map || !frames) return

    const frame = frames.frames[currentFrameIndex]
    if (!frame) return

    const canvas = document.createElement('canvas')
    const data = decodeFrame(frame.eta_base64, frames.frame_rows, frames.frame_cols)
    const depth = frames.depth_base64
      ? decodeFrame(frames.depth_base64, frames.frame_rows, frames.frame_cols)
      : undefined
    const renderFn = tidalMode ? renderTideFrameToCanvas : renderFrameToCanvas
    renderFn(canvas, data, frames.frame_rows, frames.frame_cols, depth)
    const dataUrl = canvas.toDataURL()

    // Clamp latitudes to MapLibre's Mercator limit, pass longitudes as-is
    // (MapLibre handles unwrapped longitudes like -187 or 182 correctly)
    const clampLat = (lat: number) => Math.max(-85, Math.min(85, lat))
    const b = frames.grid_bounds
    const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
      [b.lon_min, clampLat(b.lat_max)],
      [b.lon_max, clampLat(b.lat_max)],
      [b.lon_max, clampLat(b.lat_min)],
      [b.lon_min, clampLat(b.lat_min)],
    ]

    const addLayer = () => {
      if (map.getSource('wave-frame')) {
        (map.getSource('wave-frame') as any).updateImage({ url: dataUrl, coordinates })
      } else {
        map.addSource('wave-frame', { type: 'image', url: dataUrl, coordinates })
        const beforeLayer = map.getLayer('impact-circles') ? 'impact-circles' : undefined
        map.addLayer({
          id: 'wave-frame-layer',
          type: 'raster',
          source: 'wave-frame',
          paint: { 'raster-opacity': 0.7 },
        }, beforeLayer)
      }
    }

    if (map.loaded()) addLayer()
    else map.on('load', addLayer)
  }, [frames, currentFrameIndex, tidalMode])

  return (
    <div className="relative h-full w-full">
      <div ref={mapContainer} className="h-full w-full" />
      <TimelineSlider />
    </div>
  )
}
