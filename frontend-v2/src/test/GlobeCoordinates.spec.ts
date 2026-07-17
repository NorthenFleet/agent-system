import { describe, expect, it } from 'vitest'
import { clampLatitude, latLngToCartesian, normalizeLongitude } from '@/globe/coordinates'

describe('globe coordinates', () => {
  it('normalizes longitude and clamps latitude', () => {
    expect(normalizeLongitude(190)).toBe(-170)
    expect(normalizeLongitude(-190)).toBe(170)
    expect(clampLatitude(120)).toBe(90)
    expect(clampLatitude(-120)).toBe(-90)
  })

  it('keeps projected points on the requested sphere radius', () => {
    const point = latLngToCartesian(31.2304, 121.4737, 1.08)
    const length = Math.sqrt(point.x ** 2 + point.y ** 2 + point.z ** 2)
    expect(length).toBeCloseTo(1.08, 8)
  })

  it('projects the north pole to the positive y axis', () => {
    const point = latLngToCartesian(90, 0)
    expect(point.x).toBeCloseTo(0, 8)
    expect(point.y).toBeCloseTo(1, 8)
    expect(point.z).toBeCloseTo(0, 8)
  })
})
