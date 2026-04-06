import type { Simulation } from '../../types'
import { useSimulationStore } from '../../stores/simulationStore'

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-600',
  running_coarse: 'bg-blue-600 animate-pulse',
  coarse_complete: 'bg-green-600',
  running_detail: 'bg-blue-600 animate-pulse',
  complete: 'bg-green-600',
  failed: 'bg-red-600',
}

interface Props {
  simulation: Simulation
  onRunCoarse: () => void
  loading?: boolean
}

export default function SimulationControls({ simulation, onRunCoarse, loading }: Props) {
  const progress = useSimulationStore((s) => s.progress)
  const canRun = simulation.status === 'pending'
  return (
    <div className="space-y-2 border-t border-slate-700 pt-3">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${STATUS_COLORS[simulation.status] || 'bg-gray-500'}`} />
        <span className="text-sm">{simulation.status.replace(/_/g, ' ')}</span>
      </div>
      {simulation.status === 'running_coarse' && (
        <div className="mt-2">
          <div className="h-2 w-full rounded-full bg-slate-700">
            <div
              className="h-2 rounded-full bg-blue-500 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-slate-400">{Math.round(progress)}% complete</p>
        </div>
      )}
      {canRun && (
        <button
          onClick={onRunCoarse}
          disabled={loading}
          className="w-full rounded bg-orange-600 py-2 text-sm font-medium hover:bg-orange-500 disabled:opacity-50"
        >
          {loading ? 'Running...' : 'Run Coarse Simulation'}
        </button>
      )}
    </div>
  )
}
