const STOPS = [
  { value: 0, color: '#22c55e', label: '0 m' },
  { value: 2, color: '#eab308', label: '2 m' },
  { value: 5, color: '#ef4444', label: '5 m' },
  { value: 10, color: '#7c2d12', label: '10+ m' },
]

export default function ColorLegend() {
  return (
    <div className="absolute bottom-20 right-4 z-20 rounded bg-slate-800/90 p-2 text-xs">
      <div className="mb-1 font-medium text-slate-300">Wave Height</div>
      {STOPS.map((s) => (
        <div key={s.value} className="flex items-center gap-2">
          <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: s.color }} />
          <span className="text-slate-400">{s.label}</span>
        </div>
      ))}
    </div>
  )
}
