import { create } from 'zustand'

type PickPhase = 'idle' | 'picking_location' | 'picking_direction'

interface MapPickState {
  phase: PickPhase
  lat: number | null
  lon: number | null
  // Live cursor position during direction pick
  cursorLat: number | null
  cursorLon: number | null
  // Derived values (updated live during direction pick)
  direction: number | null
  magnitude: number | null

  startPicking: () => void
  setLocation: (lat: number, lon: number) => void
  updateCursor: (lat: number, lon: number) => void
  confirmDirection: () => void
  cancel: () => void
}

function computeDirectionAndMagnitude(
  lat1: number, lon1: number, lat2: number, lon2: number,
): { direction: number; magnitude: number } {
  const dLon = lon2 - lon1
  const dLat = lat2 - lat1
  // Bearing from north, clockwise
  const radians = Math.atan2(dLon * Math.cos((lat1 * Math.PI) / 180), dLat)
  let direction = (radians * 180) / Math.PI
  if (direction < 0) direction += 360

  // Distance in degrees -> magnitude mapping
  // Rough: 1 degree drag ≈ M7, 5 degrees ≈ M9
  const dist = Math.sqrt(dLat * dLat + dLon * dLon * Math.cos((lat1 * Math.PI) / 180) ** 2)
  const magnitude = Math.min(10, Math.max(5, 6.5 + dist * 0.5))

  return { direction: Math.round(direction), magnitude: Math.round(magnitude * 10) / 10 }
}

export const useMapPickStore = create<MapPickState>((set, get) => ({
  phase: 'idle',
  lat: null,
  lon: null,
  cursorLat: null,
  cursorLon: null,
  direction: null,
  magnitude: null,

  startPicking: () => set({
    phase: 'picking_location',
    lat: null, lon: null,
    cursorLat: null, cursorLon: null,
    direction: null, magnitude: null,
  }),

  setLocation: (lat, lon) => set({
    phase: 'picking_direction',
    lat, lon,
    cursorLat: lat, cursorLon: lon,
  }),

  updateCursor: (cursorLat, cursorLon) => {
    const { lat, lon } = get()
    if (lat === null || lon === null) return
    const { direction, magnitude } = computeDirectionAndMagnitude(lat, lon, cursorLat, cursorLon)
    set({ cursorLat, cursorLon, direction, magnitude })
  },

  confirmDirection: () => set({ phase: 'idle' }),

  cancel: () => set({
    phase: 'idle',
    lat: null, lon: null,
    cursorLat: null, cursorLon: null,
    direction: null, magnitude: null,
  }),
}))
