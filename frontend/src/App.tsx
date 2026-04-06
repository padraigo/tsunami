import Layout from './components/Layout'
import TopBar from './components/TopBar'
import ControlPanel from './components/ControlPanel'
import SimulationList from './components/SimulationList'
import MapView from './components/MapView/MapView'
import ColorLegend from './components/MapView/ColorLegend'
import BottomPanel from './components/BottomPanel'
import ErrorToast from './components/ErrorToast'
import { useSimulationStore } from './stores/simulationStore'
import { api } from './services/api'

export default function App() {
  const { current, coarseResult } = useSimulationStore()

  const handleExport = () => {
    if (!current) return
    window.open(api.run.exportUrl(current.uid), '_blank')
  }

  return (
    <>
      <Layout
        topBar={<TopBar onExport={current?.status === 'coarse_complete' ? handleExport : undefined} />}
        sidebar={
          <div className="space-y-4">
            <ControlPanel />
            <SimulationList />
          </div>
        }
        map={
          <div className="relative h-full w-full">
            <MapView />
            {coarseResult && <ColorLegend />}
          </div>
        }
        bottom={coarseResult ? <BottomPanel /> : undefined}
      />
      <ErrorToast />
    </>
  )
}
