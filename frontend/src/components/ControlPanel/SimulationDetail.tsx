import type { Simulation } from '../../types'

interface Props {
  simulation: Simulation
}

export default function SimulationDetail({ simulation }: Props) {
  const s = simulation
  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <div>
          <span className="text-slate-500">Latitude</span>
          <p className="font-mono">{s.earthquake_lat.toFixed(2)}</p>
        </div>
        <div>
          <span className="text-slate-500">Longitude</span>
          <p className="font-mono">{s.earthquake_lon.toFixed(2)}</p>
        </div>
        <div>
          <span className="text-slate-500">Magnitude</span>
          <p className="font-mono">{s.earthquake_magnitude}</p>
        </div>
        <div>
          <span className="text-slate-500">Direction</span>
          <p className="font-mono">{s.earthquake_direction}°</p>
        </div>
        <div>
          <span className="text-slate-500">Depth</span>
          <p className="font-mono">{s.earthquake_depth_km} km</p>
        </div>
        <div>
          <span className="text-slate-500">Grid</span>
          <p className="font-mono">{s.grid_resolution_km} km</p>
        </div>
        <div>
          <span className="text-slate-500">Duration</span>
          <p className="font-mono">{s.duration_hours} h</p>
        </div>
        <div>
          <span className="text-slate-500">Created</span>
          <p className="font-mono">{new Date(s.created_at).toLocaleDateString()}</p>
        </div>
      </div>
      {s.focus_zones.length > 0 && (
        <div className="border-t border-slate-700 pt-2">
          <span className="text-slate-500">Focus Zones</span>
          <ul className="mt-1 space-y-1">
            {s.focus_zones.map((z) => (
              <li key={z.uid} className="rounded bg-slate-700 px-2 py-1">
                {z.name} — {z.status}
                {z.max_runup_m != null && <span className="ml-1 text-amber-400">{z.max_runup_m.toFixed(1)}m runup</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
