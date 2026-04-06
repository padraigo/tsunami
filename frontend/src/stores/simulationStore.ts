import { create } from 'zustand'
import type { Simulation, CoarseResult, Preset, CreateSimulationPayload, CreateFocusZonePayload } from '../types'
import { api } from '../services/api'

interface SimulationState {
  simulations: Simulation[]
  current: Simulation | null
  coarseResult: CoarseResult | null
  presets: Preset[]
  loading: boolean
  error: string | null

  fetchSimulations: () => Promise<void>
  createSimulation: (payload: CreateSimulationPayload) => Promise<void>
  selectSimulation: (uid: string) => Promise<void>
  deleteSimulation: (uid: string) => Promise<void>
  runCoarse: () => Promise<void>
  addFocusZone: (payload: CreateFocusZonePayload) => Promise<void>
  fetchPresets: () => Promise<void>
  setError: (error: string | null) => void
}

export const useSimulationStore = create<SimulationState>((set, get) => ({
  simulations: [],
  current: null,
  coarseResult: null,
  presets: [],
  loading: false,
  error: null,

  fetchSimulations: async () => {
    set({ loading: true })
    try {
      const simulations = await api.simulations.list()
      set({ simulations, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  createSimulation: async (payload) => {
    set({ loading: true })
    try {
      const sim = await api.simulations.create(payload)
      set((s) => ({ simulations: [sim, ...s.simulations], current: sim, coarseResult: null, loading: false }))
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  selectSimulation: async (uid) => {
    set({ loading: true })
    try {
      const sim = await api.simulations.get(uid)
      let coarseResult: CoarseResult | null = null
      if (sim.status !== 'pending') {
        try { coarseResult = await api.run.coarseResult(uid) } catch { /* no results yet */ }
      }
      set({ current: sim, coarseResult, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  deleteSimulation: async (uid) => {
    try {
      await api.simulations.delete(uid)
      set((s) => ({
        simulations: s.simulations.filter((sim) => sim.uid !== uid),
        current: s.current?.uid === uid ? null : s.current,
        coarseResult: s.current?.uid === uid ? null : s.coarseResult,
      }))
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  runCoarse: async () => {
    const { current } = get()
    if (!current) return
    set({ loading: true })
    try {
      set((s) => ({ current: s.current ? { ...s.current, status: 'running_coarse' as const } : null }))
      const result = await api.run.coarse(current.uid)
      const sim = await api.simulations.get(current.uid)
      set({ current: sim, coarseResult: result, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  addFocusZone: async (payload) => {
    const { current } = get()
    if (!current) return
    try {
      const zone = await api.focusZones.create(current.uid, payload)
      set((s) => ({
        current: s.current ? { ...s.current, focus_zones: [...s.current.focus_zones, zone] } : null,
      }))
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  fetchPresets: async () => {
    try {
      const presets = await api.presets.locations()
      set({ presets })
    } catch (e: any) {
      set({ error: e.message })
    }
  },

  setError: (error) => set({ error }),
}))
