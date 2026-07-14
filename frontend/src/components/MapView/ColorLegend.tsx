import { useSimulationStore } from '../../stores/simulationStore'

const WAVE_STOPS = [
  { value: 0, color: '#22c55e', label: '0 m' },
  { value: 2, color: '#eab308', label: '2 m' },
  { value: 5, color: '#ef4444', label: '5 m' },
  { value: 10, color: '#7c2d12', label: '10+ m' },
]

const DEPTH_STOPS = [
  { color: '#ffffff', label: '4000+ m elev' },
  { color: '#e6b440', label: '2000 m elev' },
  { color: '#b4a028', label: '200 m elev' },
  { color: '#50a03c', label: 'Sea level' },
  { color: '#1eb4ff', label: '200 m depth' },
  { color: '#0a289b', label: '8000+ m depth' },
]

export default function ColorLegend() {
  const mapMode = useSimulationStore((s) => s.mapMode)
  const stops = mapMode === 'elevation' ? DEPTH_STOPS : WAVE_STOPS

  return (
    <div className="absolute bottom-20 right-4 z-20 rounded bg-slate-800/90 p-2 text-xs">
      <div className="mb-1 font-medium text-slate-300">
        {mapMode === 'elevation' ? 'Elevation / Depth' : 'Wave Height'}
      </div>
      {stops.map((s, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: s.color }} />
          <span className="text-slate-400">{'label' in s ? s.label : ''}</span>
        </div>
      ))}
    </div>
  )
}
