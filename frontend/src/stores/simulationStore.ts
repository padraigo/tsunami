import { create } from 'zustand'
import type { Simulation, CoarseResult, Preset, CreateSimulationPayload, CreateFocusZonePayload, FramesResponse, DetailZoneResult } from '../types'
import { api } from '../services/api'
import { simulationWS } from '../services/websocket'

interface SimulationState {
  simulations: Simulation[]
  current: Simulation | null
  coarseResult: CoarseResult | null
  frames: FramesResponse | null
  detailZones: DetailZoneResult[]
  currentFrameIndex: number
  isPlaying: boolean
  progress: number
  presets: Preset[]
  tidalMode: boolean
  loading: boolean
  error: string | null

  computeTides: (startDatetime: string) => Promise<void>
  exitTidalMode: () => void
  fetchSimulations: () => Promise<void>
  createSimulation: (payload: CreateSimulationPayload) => Promise<void>
  selectSimulation: (uid: string) => Promise<void>
  deleteSimulation: (uid: string) => Promise<void>
  runCoarse: () => Promise<void>
  addFocusZone: (payload: CreateFocusZonePayload) => Promise<void>
  fetchPresets: () => Promise<void>
  fetchFrames: () => Promise<void>
  fetchDetailResults: () => Promise<void>
  setFrameIndex: (index: number) => void
  togglePlayback: () => void
  setProgress: (progress: number) => void
  setError: (error: string | null) => void
}

export const useSimulationStore = create<SimulationState>((set, get) => ({
  simulations: [],
  current: null,
  coarseResult: null,
  frames: null,
  detailZones: [],
  currentFrameIndex: 0,
  isPlaying: false,
  progress: 0,
  tidalMode: false,
  presets: [],
  loading: false,
  error: null,

  computeTides: async (startDatetime: string) => {
    set({ loading: true, tidalMode: true, frames: null, currentFrameIndex: 0 })
    try {
      const frames = await api.tides.compute({ start_datetime: startDatetime, duration_hours: 25.0, num_frames: 50, resolution_km: 100.0 })
      set({ frames, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false, tidalMode: false })
    }
  },

  exitTidalMode: () => set({ tidalMode: false, frames: null, currentFrameIndex: 0, isPlaying: false }),

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
      set({ current: sim, coarseResult, frames: null, detailZones: [], currentFrameIndex: 0, isPlaying: false, progress: 0 })
      // Fetch frames and detail results for completed simulations
      if (coarseResult) {
        await get().fetchFrames()
        await get().fetchDetailResults()
      }
      set({ loading: false })
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
    set({ loading: true, progress: 0 })
    let unsub: (() => void) | undefined
    try {
      set((s) => ({ current: s.current ? { ...s.current, status: 'running_coarse' as const } : null }))

      // Connect WebSocket for progress updates
      simulationWS.connect(current.uid)
      unsub = simulationWS.subscribe((msg) => {
        if (msg.type === 'coarse_progress' && typeof msg.percent === 'number') {
          set({ progress: msg.percent as number })
        }
      })

      const result = await api.run.coarse(current.uid)

      const sim = await api.simulations.get(current.uid)
      set({ current: sim, coarseResult: result, loading: false })

      // Auto-fetch frames and detail results after run completes
      await get().fetchFrames()
      await get().fetchDetailResults()
    } catch (e: any) {
      set({ error: e.message, loading: false })
    } finally {
      unsub?.()
      simulationWS.disconnect()
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

  fetchFrames: async () => {
    const { current } = get()
    if (!current) return
    try {
      const frames = await api.run.frames(current.uid)
      set({ frames })
    } catch { /* no frames available */ }
  },

  fetchDetailResults: async () => {
    const { current } = get()
    if (!current) return
    try {
      const data = await api.run.detailResults(current.uid)
      set({ detailZones: data.zones })
    } catch { /* no detail results */ }
  },

  setFrameIndex: (index: number) => set({ currentFrameIndex: index }),

  togglePlayback: () => set((s) => ({ isPlaying: !s.isPlaying })),

  setProgress: (progress: number) => set({ progress }),

  setError: (error) => set({ error }),
}))
