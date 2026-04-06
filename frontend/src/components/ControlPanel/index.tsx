import { useEffect, useState } from 'react'
import { useSimulationStore } from '../../stores/simulationStore'
import type { Preset } from '../../types'
import EarthquakeForm from './EarthquakeForm'
import PresetSelector from './PresetSelector'
import SimulationControls from './SimulationControls'

export default function ControlPanel() {
  const { current, presets, loading, fetchPresets, createSimulation, runCoarse } = useSimulationStore()
  const [selectedPreset, setSelectedPreset] = useState<Preset | null>(null)

  useEffect(() => { fetchPresets() }, [fetchPresets])

  const handleDeselect = () => {
    useSimulationStore.setState({ current: null, coarseResult: null, frames: null })
  }

  return (
    <div className="space-y-4">
      {!current ? (
        <>
          <PresetSelector presets={presets} onSelect={setSelectedPreset} />
          <div className="my-2 border-t border-slate-700" />
          <EarthquakeForm onSubmit={createSimulation} loading={loading} preset={selectedPreset} />
        </>
      ) : (
        <>
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-sm font-semibold">{current.name}</h2>
              <p className="text-xs text-slate-400">
                M{current.earthquake_magnitude} at ({current.earthquake_lat.toFixed(1)}, {current.earthquake_lon.toFixed(1)})
              </p>
              <p className="text-xs text-slate-400">
                {current.grid_resolution_km}km grid, {current.duration_hours}h duration
              </p>
            </div>
            <button onClick={handleDeselect} className="text-xs text-slate-400 hover:text-white">
              ✕ New
            </button>
          </div>
          <SimulationControls simulation={current} onRunCoarse={runCoarse} loading={loading} />
        </>
      )}
    </div>
  )
}
