import type { ImpactPoint } from '../../types'

interface Props { impacts: ImpactPoint[] }

export default function ImpactList({ impacts }: Props) {
  if (!impacts.length) return <p className="text-sm text-slate-400">No impacts detected.</p>
  const sorted = [...impacts].sort((a, b) => b.max_height - a.max_height)
  return (
    <div className="max-h-48 overflow-y-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-slate-400">
          <tr>
            <th className="pb-1 pr-4">Location</th>
            <th className="pb-1 pr-4">Height (m)</th>
            <th className="pb-1">Arrival</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((imp, i) => (
            <tr key={`${imp.lat}-${imp.lon}-${i}`} className="border-t border-slate-700">
              <td className="py-1 pr-4">{imp.lat.toFixed(2)}, {imp.lon.toFixed(2)}</td>
              <td className="py-1 pr-4 font-medium" style={{ color: imp.max_height > 5 ? '#ef4444' : imp.max_height > 2 ? '#eab308' : '#22c55e' }}>
                {imp.max_height.toFixed(1)}
              </td>
              <td className="py-1">{Math.round(imp.arrival_time_s / 60)} min</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
