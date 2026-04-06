import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useSimulationStore } from '../../stores/simulationStore'
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
      // Transparent
      imageData.data[idx] = 0
      imageData.data[idx + 1] = 0
      imageData.data[idx + 2] = 0
      imageData.data[idx + 3] = 0
    } else if (v < 0.5) {
      // Blue
      const t = v / 0.5
      imageData.data[idx] = 0
      imageData.data[idx + 1] = Math.round(100 + 155 * t)
      imageData.data[idx + 2] = 255
      imageData.data[idx + 3] = Math.round(100 + 155 * t)
    } else if (v < 2) {
      // Green to yellow
      const t = (v - 0.5) / 1.5
      imageData.data[idx] = Math.round(255 * t)
      imageData.data[idx + 1] = 200
      imageData.data[idx + 2] = Math.round(255 * (1 - t))
      imageData.data[idx + 3] = 200
    } else if (v < 5) {
      // Yellow to red
      const t = (v - 2) / 3
      imageData.data[idx] = 255
      imageData.data[idx + 1] = Math.round(200 * (1 - t))
      imageData.data[idx + 2] = 0
      imageData.data[idx + 3] = 220
    } else {
      // Red/dark
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
  const { current, coarseResult, frames, currentFrameIndex } = useSimulationStore()

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

  // Earthquake marker
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
      [bounds.lon_min, bounds.lat_max], // top-left
      [bounds.lon_max, bounds.lat_max], // top-right
      [bounds.lon_max, bounds.lat_min], // bottom-right
      [bounds.lon_min, bounds.lat_min], // bottom-left
    ]

    const addLayer = () => {
      if (map.getSource('wave-frame')) {
        (map.getSource('wave-frame') as any).updateImage({ url: dataUrl, coordinates })
      } else {
        map.addSource('wave-frame', {
          type: 'image',
          url: dataUrl,
          coordinates,
        })
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
