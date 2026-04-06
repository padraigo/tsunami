import { useEffect, useState } from 'react'
import { useSimulationStore } from '../../stores/simulationStore'
import type { Preset } from '../../types'
import EarthquakeForm from './EarthquakeForm'
import PresetSelector from './PresetSelector'
import SimulationControls from './SimulationControls'
import SimulationDetail from './SimulationDetail'

export default function ControlPanel() {
  const { current, presets, loading, fetchPresets, createSimulation, runCoarse } = useSimulationStore()
  const [selectedPreset, setSelectedPreset] = useState<Preset | null>(null)
  const [editing, setEditing] = useState(false)

  useEffect(() => { fetchPresets() }, [fetchPresets])
  // Reset editing state when simulation changes
  useEffect(() => { setEditing(false) }, [current?.uid])

  const handleDeselect = () => {
    useSimulationStore.setState({ current: null, coarseResult: null, frames: null })
  }

  const handleClone = () => {
    if (!current) return
    // Deselect current, and set a preset-like object to populate the form
    setSelectedPreset({
      name: `${current.name} (copy)`,
      lat: current.earthquake_lat,
      lon: current.earthquake_lon,
      magnitude: current.earthquake_magnitude,
      direction: current.earthquake_direction,
    })
    useSimulationStore.setState({ current: null, coarseResult: null, frames: null })
  }

  // No simulation selected — show create form
  if (!current) {
    return (
      <div className="space-y-4">
        <PresetSelector presets={presets} onSelect={setSelectedPreset} />
        <div className="my-2 border-t border-slate-700" />
        <EarthquakeForm onSubmit={createSimulation} loading={loading} preset={selectedPreset} />
      </div>
    )
  }

  // Simulation selected
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold">{current.name}</h2>
          <p className="text-xs text-slate-400">
            M{current.earthquake_magnitude} — {current.status.replace(/_/g, ' ')}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleClone} className="text-xs text-slate-400 hover:text-blue-400" title="Clone with new settings">
            Clone
          </button>
          <button onClick={handleDeselect} className="text-xs text-slate-400 hover:text-white" title="Create new simulation">
            ✕ New
          </button>
        </div>
      </div>

      {/* Run controls */}
      <SimulationControls simulation={current} onRunCoarse={runCoarse} loading={loading} />

      {/* Detail toggle */}
      <button
        onClick={() => setEditing(!editing)}
        className="w-full text-left text-xs text-slate-400 hover:text-white"
      >
        {editing ? '▾ Hide details' : '▸ Show details'}
      </button>

      {editing && <SimulationDetail simulation={current} />}
    </div>
  )
}
