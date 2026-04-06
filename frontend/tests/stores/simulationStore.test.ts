import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../src/services/api', () => ({
  api: {
    simulations: {
      list: vi.fn().mockResolvedValue([{ uid: 'sim-1', name: 'Test', status: 'pending' }]),
      create: vi.fn().mockResolvedValue({ uid: 'sim-new', name: 'New', status: 'pending', focus_zones: [] }),
      get: vi.fn().mockResolvedValue({ uid: 'sim-1', name: 'Test', status: 'pending', focus_zones: [] }),
      delete: vi.fn().mockResolvedValue(undefined),
    },
    run: { coarse: vi.fn().mockResolvedValue({ status: 'coarse_complete', impacts: [], suggested_zones: [] }), coarseResult: vi.fn() },
    focusZones: { create: vi.fn().mockResolvedValue({ uid: 'z-1', name: 'Zone 1', status: 'pending' }) },
    presets: { locations: vi.fn().mockResolvedValue([{ name: 'Tohoku', lat: 38, lon: 142, magnitude: 9, direction: 290 }]) },
  },
}))

import { useSimulationStore } from '../../src/stores/simulationStore'

beforeEach(() => {
  useSimulationStore.setState({ simulations: [], current: null, coarseResult: null, presets: [], loading: false, error: null })
})

describe('simulationStore', () => {
  it('fetchSimulations populates list', async () => {
    await useSimulationStore.getState().fetchSimulations()
    expect(useSimulationStore.getState().simulations).toHaveLength(1)
  })

  it('createSimulation adds to list and sets current', async () => {
    await useSimulationStore.getState().createSimulation({ name: 'New', earthquake_lat: 0, earthquake_lon: 100, earthquake_magnitude: 8, earthquake_direction: 270 } as any)
    expect(useSimulationStore.getState().current?.uid).toBe('sim-new')
  })

  it('fetchPresets populates presets', async () => {
    await useSimulationStore.getState().fetchPresets()
    expect(useSimulationStore.getState().presets).toHaveLength(1)
  })
})
