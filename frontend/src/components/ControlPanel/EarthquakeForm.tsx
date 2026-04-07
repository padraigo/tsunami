import { useState, useEffect } from 'react'
import type { CreateSimulationPayload, Preset } from '../../types'
import { useMapPickStore } from '../../stores/mapPickStore'

interface Props {
  onSubmit: (payload: CreateSimulationPayload) => void
  loading?: boolean
  preset?: Preset | null
}

export default function EarthquakeForm({ onSubmit, loading, preset }: Props) {
  const [name, setName] = useState('New Simulation')
  const [lat, setLat] = useState(0)
  const [lon, setLon] = useState(100)
  const [magnitude, setMagnitude] = useState(8.0)
  const [direction, setDirection] = useState(270)
  const [depthKm, setDepthKm] = useState(15)
  const [earthquakeDatetime, setEarthquakeDatetime] = useState('')
  const [durationHours, setDurationHours] = useState(1.0)
  const [gridResolutionKm, setGridResolutionKm] = useState(20.0)

  const pick = useMapPickStore()

  // When a preset is selected, populate the form
  useEffect(() => {
    if (preset) {
      setName(preset.name)
      setLat(preset.lat)
      setLon(preset.lon)
      setMagnitude(preset.magnitude)
      setDirection(preset.direction)
    }
  }, [preset])

  // When map pick updates, sync to form fields
  useEffect(() => {
    if (pick.lat !== null && pick.lon !== null) {
      setLat(Math.round(pick.lat * 10) / 10)
      setLon(Math.round(pick.lon * 10) / 10)
      setName(`Custom (${pick.lat.toFixed(1)}, ${pick.lon.toFixed(1)})`)
    }
  }, [pick.lat, pick.lon])

  useEffect(() => {
    if (pick.direction !== null) setDirection(pick.direction)
  }, [pick.direction])

  useEffect(() => {
    if (pick.magnitude !== null) setMagnitude(pick.magnitude)
  }, [pick.magnitude])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit({
      name,
      earthquake_lat: lat,
      earthquake_lon: lon,
      earthquake_magnitude: magnitude,
      earthquake_direction: direction,
      earthquake_depth_km: depthKm,
      earthquake_datetime: earthquakeDatetime ? new Date(earthquakeDatetime).toISOString() : undefined,
      duration_hours: durationHours,
      grid_resolution_km: gridResolutionKm,
    })
  }

  const isPicking = pick.phase !== 'idle'

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Earthquake Source</h2>
        {!isPicking ? (
          <button
            type="button"
            onClick={pick.startPicking}
            className="rounded bg-amber-600 px-2 py-0.5 text-xs font-medium hover:bg-amber-500"
          >
            Pick on Map
          </button>
        ) : (
          <button
            type="button"
            onClick={pick.cancel}
            className="rounded bg-red-600 px-2 py-0.5 text-xs font-medium hover:bg-red-500"
          >
            Cancel
          </button>
        )}
      </div>

      {isPicking && (
        <div className="rounded bg-amber-900/50 border border-amber-600/50 px-3 py-2 text-xs">
          {pick.phase === 'picking_location' && (
            <p>Click the map to set the <strong>epicenter location</strong>.</p>
          )}
          {pick.phase === 'picking_direction' && (
            <p>
              Now drag away from the epicenter to set <strong>direction</strong> and <strong>magnitude</strong>. Click to confirm.
              <br />
              <span className="text-amber-300">
                Dir: {pick.direction ?? '—'}°  |  Mag: {pick.magnitude ?? '—'}
              </span>
            </p>
          )}
        </div>
      )}

      <label className="block">
        <span className="text-xs text-slate-400">Name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs text-slate-400">Latitude</span>
          <input type="number" step="0.1" min={-90} max={90} value={lat} onChange={(e) => setLat(+e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Longitude</span>
          <input type="number" step="0.1" min={-180} max={180} value={lon} onChange={(e) => setLon(+e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs text-slate-400">Magnitude</span>
          <input type="number" step="0.1" min={5} max={10} value={magnitude} onChange={(e) => setMagnitude(+e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Direction (deg)</span>
          <input type="number" step="1" min={0} max={359} value={direction} onChange={(e) => setDirection(+e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
        </label>
      </div>

      <label className="block">
        <span className="text-xs text-slate-400">Depth (km)</span>
        <input type="number" step="1" min={0} max={700} value={depthKm} onChange={(e) => setDepthKm(+e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
      </label>

      <label className="block">
        <span className="text-xs text-slate-400">Date/Time (UTC, optional)</span>
        <input type="datetime-local" value={earthquakeDatetime}
               onChange={(e) => setEarthquakeDatetime(e.target.value)}
               className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
      </label>

      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 pt-2">Simulation Settings</h2>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs text-slate-400">Duration (hours)</span>
          <input type="number" step="0.5" min={0.5} max={48} value={durationHours} onChange={(e) => setDurationHours(+e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Grid (km)</span>
          <input type="number" step="1" min={1} max={100} value={gridResolutionKm} onChange={(e) => setGridResolutionKm(+e.target.value)} className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm" />
        </label>
      </div>

      <p className="text-xs text-slate-500">
        Smaller grid = more detail but slower. Try 20-50km for quick runs, 5-10km for detail.
      </p>

      <button type="submit" disabled={loading || isPicking} className="w-full rounded bg-emerald-600 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50">
        {loading ? 'Creating...' : 'Create Simulation'}
      </button>
    </form>
  )
}
