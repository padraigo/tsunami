import type { SuggestedZone, CreateFocusZonePayload } from '../../types'

interface Props {
  zones: SuggestedZone[]
  onAddZone: (payload: CreateFocusZonePayload) => void
}

export default function SuggestedZones({ zones, onAddZone }: Props) {
  if (!zones.length) return <p className="text-sm text-slate-400">No zones suggested.</p>
  return (
    <div className="space-y-2">
      {zones.map((z, i) => (
        <div key={i} className="flex items-center justify-between rounded bg-slate-700 p-2 text-xs">
          <div>
            <span className="font-medium">Zone {i + 1}</span>
            <span className="ml-2 text-slate-400">
              Max {z.max_impact_height.toFixed(1)}m, {z.impact_count} impacts
            </span>
          </div>
          <button
            onClick={() => onAddZone({
              name: `Zone ${i + 1}`,
              lat_min: z.lat_min, lat_max: z.lat_max,
              lon_min: z.lon_min, lon_max: z.lon_max,
              source: 'auto',
            })}
            className="rounded bg-blue-600 px-2 py-1 hover:bg-blue-500"
          >
            Add
          </button>
        </div>
      ))}
    </div>
  )
}
