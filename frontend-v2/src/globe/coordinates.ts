export interface CartesianPoint {
  x: number
  y: number
  z: number
}

export function clampLatitude(latitude: number) {
  return Math.max(-90, Math.min(90, latitude))
}

export function normalizeLongitude(longitude: number) {
  return ((longitude + 180) % 360 + 360) % 360 - 180
}

export function latLngToCartesian(latitude: number, longitude: number, radius = 1): CartesianPoint {
  const lat = clampLatitude(latitude)
  const lng = normalizeLongitude(longitude)
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return {
    x: -radius * Math.sin(phi) * Math.cos(theta),
    y: radius * Math.cos(phi),
    z: radius * Math.sin(phi) * Math.sin(theta)
  }
}
