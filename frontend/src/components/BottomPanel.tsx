import { useState } from 'react'
import { useSimulationStore } from '../stores/simulationStore'
import ImpactList from './Results/ImpactList'
import SuggestedZones from './Results/SuggestedZones'

export default function BottomPanel() {
  const { coarseResult, addFocusZone } = useSimulationStore()
  const [tab, setTab] = useState<'impacts' | 'zones'>('impacts')

  if (!coarseResult) return null

  return (
    <div>
      <div className="mb-2 flex gap-2 border-b border-slate-700 pb-2">
        <button onClick={() => setTab('impacts')} className={`text-xs font-medium ${tab === 'impacts' ? 'text-white' : 'text-slate-400'}`}>
          Impacts ({coarseResult.impacts.length})
        </button>
        <button onClick={() => setTab('zones')} className={`text-xs font-medium ${tab === 'zones' ? 'text-white' : 'text-slate-400'}`}>
          Suggested Zones ({coarseResult.suggested_zones.length})
        </button>
      </div>
      {tab === 'impacts' && <ImpactList impacts={coarseResult.impacts} />}
      {tab === 'zones' && <SuggestedZones zones={coarseResult.suggested_zones} onAddZone={addFocusZone} />}
    </div>
  )
}
