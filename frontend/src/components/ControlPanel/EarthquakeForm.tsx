import { useState } from 'react'
import type { CreateSimulationPayload } from '../../types'

interface Props {
  onSubmit: (payload: CreateSimulationPayload) => void
  loading?: boolean
}

export default function EarthquakeForm({ onSubmit, loading }: Props) {
  const [name, setName] = useState('New Simulation')
  const [lat, setLat] = useState(0)
  const [lon, setLon] = useState(100)
  const [magnitude, setMagnitude] = useState(8.0)
  const [direction, setDirection] = useState(270)
  const [depthKm, setDepthKm] = useState(15)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit({
      name,
      earthquake_lat: lat,
      earthquake_lon: lon,
      earthquake_magnitude: magnitude,
      earthquake_direction: direction,
      earthquake_depth_km: depthKm,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Earthquake Source</h2>

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

      <button type="submit" disabled={loading} className="w-full rounded bg-emerald-600 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50">
        {loading ? 'Creating...' : 'Create Simulation'}
      </button>
    </form>
  )
}
