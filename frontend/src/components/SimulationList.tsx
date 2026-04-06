import { useEffect } from 'react'
import { useSimulationStore } from '../stores/simulationStore'

export default function SimulationList() {
  const { simulations, current, fetchSimulations, selectSimulation, deleteSimulation } = useSimulationStore()

  useEffect(() => { fetchSimulations() }, [fetchSimulations])

  if (!simulations.length) return null

  return (
    <div className="space-y-1 border-t border-slate-700 pt-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">History</h3>
      {simulations.map((sim) => (
        <div
          key={sim.uid}
          className={`flex cursor-pointer items-center justify-between rounded px-2 py-1 text-xs ${current?.uid === sim.uid ? 'bg-slate-600' : 'hover:bg-slate-700'}`}
          onClick={() => selectSimulation(sim.uid)}
        >
          <span className="truncate">{sim.name}</span>
          <button
            onClick={(e) => { e.stopPropagation(); deleteSimulation(sim.uid) }}
            className="ml-2 text-slate-400 hover:text-red-400"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
