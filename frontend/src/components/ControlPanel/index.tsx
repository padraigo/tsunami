import { useEffect } from 'react'
import { useSimulationStore } from '../../stores/simulationStore'
import EarthquakeForm from './EarthquakeForm'
import PresetSelector from './PresetSelector'
import SimulationControls from './SimulationControls'

export default function ControlPanel() {
  const { current, presets, loading, fetchPresets, createSimulation, runCoarse } = useSimulationStore()

  useEffect(() => { fetchPresets() }, [fetchPresets])

  return (
    <div className="space-y-4">
      {!current ? (
        <>
          <PresetSelector presets={presets} onSelect={(p) => createSimulation({
            name: p.name,
            earthquake_lat: p.lat,
            earthquake_lon: p.lon,
            earthquake_magnitude: p.magnitude,
            earthquake_direction: p.direction,
          })} />
          <div className="my-2 border-t border-slate-700" />
          <EarthquakeForm onSubmit={createSimulation} loading={loading} />
        </>
      ) : (
        <>
          <div>
            <h2 className="text-sm font-semibold">{current.name}</h2>
            <p className="text-xs text-slate-400">
              M{current.earthquake_magnitude} at ({current.earthquake_lat.toFixed(1)}, {current.earthquake_lon.toFixed(1)})
            </p>
          </div>
          <SimulationControls simulation={current} onRunCoarse={runCoarse} loading={loading} />
        </>
      )}
    </div>
  )
}
