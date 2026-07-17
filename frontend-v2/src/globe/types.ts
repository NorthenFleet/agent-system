export type GlobeSpatialType = 'domain' | 'news' | 'vessel' | 'event'

export interface GlobeSpatialItem {
  key: string
  type: GlobeSpatialType
  id: string
  name: string
  lat: number
  lng: number
  locationLabel: string
  countLabel: string
}

export interface GlobeTrackPoint {
  lat: number
  lng: number
  timestamp?: string
}

export interface GlobeTrack {
  id: string
  active?: boolean
  points: GlobeTrackPoint[]
}
