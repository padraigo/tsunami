import { useEffect, useRef, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useSimulationStore } from '../../stores/simulationStore'
import { useMapPickStore } from '../../stores/mapPickStore'
import TimelineSlider from './TimelineSlider'
import ColorLegend from './ColorLegend'

function decodeFrame(base64: string, _rows: number, _cols: number): Float32Array {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new Float32Array(bytes.buffer)
}

function mercY(latDeg: number): number {
  const clamp = Math.max(-85, Math.min(85, latDeg))
  const latRad = (clamp * Math.PI) / 180
  return Math.log(Math.tan(Math.PI / 4 + latRad / 2))
}

type ColorFn = (raw: number, idx: number, buf: Uint8ClampedArray) => void

const waveColor: ColorFn = (raw, idx, buf) => {
  const v = Math.abs(raw)
  if (v < 0.01) { buf[idx+3] = 0; return }
  if (v < 0.5) {
    const t = v / 0.5
    buf[idx]=0; buf[idx+1]=Math.round(100+155*t); buf[idx+2]=255; buf[idx+3]=Math.round(100+155*t)
  } else if (v < 2) {
    const t = (v-0.5)/1.5
    buf[idx]=Math.round(255*t); buf[idx+1]=200; buf[idx+2]=Math.round(255*(1-t)); buf[idx+3]=200
  } else if (v < 5) {
    const t = (v-2)/3
    buf[idx]=255; buf[idx+1]=Math.round(200*(1-t)); buf[idx+2]=0; buf[idx+3]=220
  } else {
    buf[idx]=200; buf[idx+1]=0; buf[idx+2]=0; buf[idx+3]=240
  }
}

const tideColor: ColorFn = (raw, idx, buf) => {
  if (Math.abs(raw) < 0.005) { buf[idx+3] = 0; return }
  if (raw < 0) {
    const t = Math.min(1, Math.abs(raw) / 0.5)
    buf[idx]=30; buf[idx+1]=Math.round(100+155*(1-t)); buf[idx+2]=255; buf[idx+3]=Math.round(150+100*t)
  } else {
    const t = Math.min(1, raw / 0.5)
    buf[idx]=255; buf[idx+1]=Math.round(150*(1-t)); buf[idx+2]=30; buf[idx+3]=Math.round(150+100*t)
  }
}

/**
 * Render a frame to canvas with Mercator resampling.
 * Data is equirectangular (uniform lat spacing); MapLibre stretches
 * the image linearly in Mercator Y, so we pre-warp rows to compensate.
 */
function renderFrameToCanvas(
  canvas: HTMLCanvasElement,
  data: Float32Array,
  rows: number,
  cols: number,
  depth: Float32Array | undefined,
  dataLatMin: number,
  dataLatMax: number,
  boundsLatMin: number,
  boundsLatMax: number,
  colorFn: ColorFn,
): void {
  const outRows = Math.max(rows, Math.round(rows * 2))
  canvas.width = cols
  canvas.height = outRows
  const ctx = canvas.getContext('2d')!
  const imageData = ctx.createImageData(cols, outRows)
  const buf = imageData.data

  const mercMin = mercY(boundsLatMin)
  const mercMax = mercY(boundsLatMax)

  for (let canvasRow = 0; canvasRow < outRows; canvasRow++) {
    // Canvas top = north (lat_max), bottom = south (lat_min)
    const mercFrac = canvasRow / (outRows - 1)
    const mercVal = mercMax - mercFrac * (mercMax - mercMin)
    const latDeg = (2 * Math.atan(Math.exp(mercVal)) - Math.PI / 2) * 180 / Math.PI

    // Map to data row (row 0 = dataLatMin = south)
    const dataRowF = ((latDeg - dataLatMin) / (dataLatMax - dataLatMin)) * (rows - 1)
    const dataRow = Math.max(0, Math.min(rows - 1, Math.round(dataRowF)))

    for (let col = 0; col < cols; col++) {
      const dataIdx = dataRow * cols + col
      const idx = (canvasRow * cols + col) * 4
      const isLand = depth ? depth[dataIdx] <= 0 : false

      buf[idx] = 0; buf[idx+1] = 0; buf[idx+2] = 0; buf[idx+3] = 0
      if (!isLand) {
        colorFn(data[dataIdx], idx, buf)
      }
    }
  }
  ctx.putImageData(imageData, 0, 0)
}

export default function MapView() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const pickMarkerRef = useRef<maplibregl.Marker | null>(null)
  const { current, coarseResult, frames, currentFrameIndex, detailZones, tidalMode, mapMode } = useSimulationStore()
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

    return () => {
      if (map.getLayer('impact-circles')) map.removeLayer('impact-circles')
      if (map.getSource('impacts')) map.removeSource('impacts')
    }
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

    return () => {
      if (map.getLayer('zone-fill')) map.removeLayer('zone-fill')
      if (map.getLayer('zone-outline')) map.removeLayer('zone-outline')
      if (map.getSource('zones')) map.removeSource('zones')
    }
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

    return () => {
      if (map.getLayer('inundation-fill')) map.removeLayer('inundation-fill')
      if (map.getLayer('inundation-outline')) map.removeLayer('inundation-outline')
      if (map.getSource('inundation')) map.removeSource('inundation')
    }
  }, [detailZones])

  // Elevation/depth overlay — uses a server-rendered PNG directly
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    if (mapMode !== 'elevation') {
      if (map.getLayer('depth-layer')) map.removeLayer('depth-layer')
      if (map.getSource('depth-frame')) map.removeSource('depth-frame')
      if (map.getLayer('osm')) map.setPaintProperty('osm', 'raster-opacity', 1)
      return
    }

    // Use server-rendered PNG. Span: lat -85..85 (Mercator limit), lon exactly
    // -180..180 (the PNG has no wrap columns — corners must match this span)
    const pngUrl = '/api/bathymetry/global-depth.png?resolution_km=100'
    const coordinates: [[number, number], [number, number], [number, number], [number, number]] = [
      [-180, 85],
      [180, 85],
      [180, -85],
      [-180, -85],
    ]

    const addLayer = () => {
      // Dim OSM tiles so the elevation map dominates
      if (map.getLayer('osm')) map.setPaintProperty('osm', 'raster-opacity', 0.15)
      if (map.getSource('depth-frame')) {
        (map.getSource('depth-frame') as any).updateImage({ url: pngUrl, coordinates })
      } else {
        map.addSource('depth-frame', { type: 'image', url: pngUrl, coordinates })
        const beforeLayer = map.getLayer('wave-frame-layer') ? 'wave-frame-layer'
          : map.getLayer('impact-circles') ? 'impact-circles'
          : undefined
        map.addLayer({
          id: 'depth-layer',
          type: 'raster',
          source: 'depth-frame',
          paint: {
            'raster-opacity': 0.95,
          },
        }, beforeLayer)
      }
    }

    // 'idle' (unlike 'load') fires again after every style settle, and the
    // listener is removed on cleanup so a stale callback can't re-add the
    // overlay after toggling back to standard mode.
    if (map.isStyleLoaded()) addLayer()
    else map.once('idle', addLayer)

    return () => {
      map.off('idle', addLayer)
      if (map.getLayer('depth-layer')) map.removeLayer('depth-layer')
      if (map.getSource('depth-frame')) map.removeSource('depth-frame')
    }
  }, [mapMode])

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
    const b = frames.grid_bounds
    // Data lat range: the actual grid the backend computed on
    // For tides: -80..80 (create_grid bounds), for waves: from domain_for_magnitude
    // A safe approximation: use the image bounds shrunk by half a cell
    const dlat = (b.lat_max - b.lat_min) / frames.frame_rows
    const dataLatMin = b.lat_min + dlat / 2
    const dataLatMax = b.lat_max - dlat / 2
    renderFrameToCanvas(
      canvas, data, frames.frame_rows, frames.frame_cols, depth,
      dataLatMin, dataLatMax, b.lat_min, b.lat_max,
      tidalMode ? tideColor : waveColor,
    )
    const dataUrl = canvas.toDataURL()

    // Clamp latitudes to MapLibre's Mercator limit, pass longitudes as-is
    // (MapLibre handles unwrapped longitudes like -187 or 182 correctly)
    const clampLat = (lat: number) => Math.max(-85, Math.min(85, lat))
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

    return () => {
      if (map.getLayer('wave-frame-layer')) map.removeLayer('wave-frame-layer')
      if (map.getSource('wave-frame')) map.removeSource('wave-frame')
    }
  }, [frames, currentFrameIndex, tidalMode])

  return (
    <div className="relative h-full w-full">
      <div ref={mapContainer} className="h-full w-full" />
      <button
        onClick={() => useSimulationStore.getState().toggleMapMode()}
        className={`absolute top-2 left-2 z-20 rounded px-3 py-1.5 text-xs font-medium shadow transition-colors ${
          mapMode === 'elevation'
            ? 'bg-emerald-600 text-white hover:bg-emerald-700'
            : 'bg-slate-700/90 text-slate-300 hover:bg-slate-600'
        }`}
      >
        {mapMode === 'elevation' ? 'Elevation View' : 'Standard Map'}
      </button>
      <ColorLegend />
      <TimelineSlider />
    </div>
  )
}
