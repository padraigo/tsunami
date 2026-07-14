import type {
  Simulation,
  FocusZone,
  CoarseResult,
  Preset,
  CreateSimulationPayload,
  CreateFocusZonePayload,
  TideComputePayload,
  FramesResponse,
  DetailResultsResponse,
} from '../types'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${text}`)
  }
  if (res.status === 204) return undefined as unknown as T
  return res.json() as Promise<T>
}

export const api = {
  simulations: {
    list: () => apiFetch<Simulation[]>('/simulations'),
    create: (payload: CreateSimulationPayload) =>
      apiFetch<Simulation>('/simulations', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    get: (uid: string) => apiFetch<Simulation>(`/simulations/${uid}`),
    delete: (uid: string) =>
      apiFetch<void>(`/simulations/${uid}`, { method: 'DELETE' }),
  },
  focusZones: {
    list: (uid: string) =>
      apiFetch<FocusZone[]>(`/simulations/${uid}/focus-zones`),
    create: (uid: string, payload: CreateFocusZonePayload) =>
      apiFetch<FocusZone>(`/simulations/${uid}/focus-zones`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    delete: (simUid: string, zoneUid: string) =>
      apiFetch<void>(`/simulations/${simUid}/focus-zones/${zoneUid}`, {
        method: 'DELETE',
      }),
  },
  run: {
    coarse: (uid: string) =>
      apiFetch<CoarseResult>(`/simulations/${uid}/run-coarse`, { method: 'POST' }),
    coarseResult: (uid: string) =>
      apiFetch<CoarseResult>(`/simulations/${uid}/coarse-result`),
    frames: (uid: string) => apiFetch<FramesResponse>(`/simulations/${uid}/frames`),
    detailResults: (uid: string) => apiFetch<DetailResultsResponse>(`/simulations/${uid}/detail-results`),
    exportUrl: (uid: string) => `/api/simulations/${uid}/export?format=geojson`,
  },
  tides: {
    compute: (payload: TideComputePayload) =>
      apiFetch<FramesResponse>('/tides/compute', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },
  bathymetry: {
    globalDepth: (resolution_km?: number) =>
      apiFetch<FramesResponse>(`/bathymetry/global-depth?resolution_km=${resolution_km ?? 100}`),
  },
  presets: {
    locations: () => apiFetch<Preset[]>('/presets/locations'),
  },
}
