export type SimulationStatus =
  | 'pending'
  | 'running_coarse'
  | 'coarse_complete'
  | 'running_detail'
  | 'complete'
  | 'failed'

export type FocusZoneStatus = 'pending' | 'running' | 'complete' | 'failed'
export type FocusZoneSource = 'auto' | 'preset' | 'user'

export interface FocusZone {
  uid: string
  name: string
  status: FocusZoneStatus
  source: FocusZoneSource
  lat_min: number
  lat_max: number
  lon_min: number
  lon_max: number
  grid_resolution_m: number
  max_runup_m?: number
}

export interface Simulation {
  uid: string
  name: string
  status: SimulationStatus
  created_at: string
  earthquake_lat: number
  earthquake_lon: number
  earthquake_magnitude: number
  earthquake_direction: number
  earthquake_depth_km: number
  grid_resolution_km: number
  duration_hours: number
  focus_zones: FocusZone[]
}

export interface ImpactPoint {
  lat: number
  lon: number
  max_height: number
  arrival_time_s: number
}

export interface SuggestedZone {
  lat_min: number
  lat_max: number
  lon_min: number
  lon_max: number
  max_impact_height: number
  impact_count: number
}

export interface CoarseResult {
  status: string
  impacts: ImpactPoint[]
  suggested_zones: SuggestedZone[]
  max_wave_height?: number
}

export interface Preset {
  name: string
  lat: number
  lon: number
  magnitude: number
  direction: number
}

export interface WsMessage {
  type: string
  simulation_uid?: string
  [key: string]: unknown
}

export interface CreateSimulationPayload {
  name: string
  earthquake_lat: number
  earthquake_lon: number
  earthquake_magnitude: number
  earthquake_direction: number
  earthquake_depth_km?: number
  grid_resolution_km?: number
  duration_hours?: number
}

export interface CreateFocusZonePayload {
  name: string
  lat_min: number
  lat_max: number
  lon_min: number
  lon_max: number
  source: string
  grid_resolution_m?: number
}

export interface FrameData {
  time_s: number
  eta_base64: string
}

export interface FramesResponse {
  grid_bounds: {
    lat_min: number
    lat_max: number
    lon_min: number
    lon_max: number
  }
  frame_rows: number
  frame_cols: number
  frames: FrameData[]
}
