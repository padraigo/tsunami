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
): void {
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const imageData = ctx.createImageData(cols, rows)
  for (let i = 0; i < data.length; i++) {
    const v = Math.abs(data[i])
    const idx = i * 4
    if (v < 0.01) {
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

export default function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const pickMarkerRef = useRef<maplibregl.Marker | null>(null)
  const { current, coarseResult, frames, currentFrameIndex } = useSimulationStore()
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

  // Wave animation frame
  useEffect(() => {
    const map = mapRef.current
    if (!map || !frames) return

    const frame = frames.frames[currentFrameIndex]
    if (!frame) return

    const canvas = document.createElement('canvas')
    const data = decodeFrame(frame.eta_base64, frames.frame_rows, frames.frame_cols)
    renderFrameToCanvas(canvas, data, frames.frame_rows, frames.frame_cols)
    const dataUrl = canvas.toDataURL()

    const bounds = frames.grid_bounds
    const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
      [bounds.lon_min, bounds.lat_max],
      [bounds.lon_max, bounds.lat_max],
      [bounds.lon_max, bounds.lat_min],
      [bounds.lon_min, bounds.lat_min],
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
  }, [frames, currentFrameIndex])

  return (
    <div className="relative h-full w-full">
      <div ref={mapContainer} className="h-full w-full" />
      <TimelineSlider />
    </div>
  )
}
