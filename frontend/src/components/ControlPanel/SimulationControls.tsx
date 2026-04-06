import type { Simulation } from '../../types'

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
  const canRun = simulation.status === 'pending'
  return (
    <div className="space-y-2 border-t border-slate-700 pt-3">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${STATUS_COLORS[simulation.status] || 'bg-gray-500'}`} />
        <span className="text-sm">{simulation.status.replace(/_/g, ' ')}</span>
      </div>
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
