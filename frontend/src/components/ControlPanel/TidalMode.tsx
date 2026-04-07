import { useState } from 'react'
import { useSimulationStore } from '../../stores/simulationStore'

export default function TidalMode() {
  const { tidalMode, loading, computeTides, exitTidalMode } = useSimulationStore()
  const [datetime, setDatetime] = useState(() => {
    const now = new Date()
    return now.toISOString().slice(0, 16)
  })

  if (tidalMode) {
    return (
      <div className="space-y-2 rounded bg-cyan-900/30 border border-cyan-700/50 p-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-cyan-300">Tidal Visualization</h3>
          <button onClick={exitTidalMode} className="text-xs text-slate-400 hover:text-white">✕ Exit</button>
        </div>
        <p className="text-xs text-slate-400">Showing global tides. Use the timeline to animate.</p>
      </div>
    )
  }

  return (
    <div className="space-y-2 rounded bg-slate-700/50 p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Global Tides</h3>
      <label className="block">
        <span className="text-xs text-slate-400">Start Date/Time (UTC)</span>
        <input
          type="datetime-local"
          value={datetime}
          onChange={(e) => setDatetime(e.target.value)}
          className="mt-1 block w-full rounded bg-slate-700 px-2 py-1 text-sm"
        />
      </label>
      <button
        onClick={() => computeTides(new Date(datetime).toISOString())}
        disabled={loading}
        className="w-full rounded bg-cyan-600 py-1.5 text-xs font-medium hover:bg-cyan-500 disabled:opacity-50"
      >
        {loading ? 'Computing...' : 'Show Global Tides'}
      </button>
      {loading && (
        <div className="space-y-1">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700">
            <div className="h-full animate-[loading_2s_ease-in-out_infinite] rounded-full bg-cyan-500"
                 style={{ width: '40%', animation: 'loading 2s ease-in-out infinite' }} />
          </div>
          <p className="text-xs text-slate-400">Computing 50 tidal frames across 25 hours...</p>
          <style>{`
            @keyframes loading {
              0% { transform: translateX(-100%); }
              50% { transform: translateX(150%); }
              100% { transform: translateX(-100%); }
            }
          `}</style>
        </div>
      )}
    </div>
  )
}
