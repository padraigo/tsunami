import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../../src/services/api'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function okJson(data: unknown, status = 200) {
  return Promise.resolve({ ok: true, status, json: () => Promise.resolve(data), text: () => Promise.resolve(JSON.stringify(data)) })
}

beforeEach(() => mockFetch.mockReset())

describe('api.simulations', () => {
  it('list fetches GET /api/simulations', async () => {
    mockFetch.mockReturnValueOnce(okJson([{ uid: 'abc' }]))
    const result = await api.simulations.list()
    expect(mockFetch).toHaveBeenCalledWith('/api/simulations', expect.any(Object))
    expect(result).toEqual([{ uid: 'abc' }])
  })

  it('create posts JSON body', async () => {
    const payload = { name: 'Test', earthquake_lat: 35, earthquake_lon: 140, earthquake_magnitude: 7.5, earthquake_direction: 0 }
    mockFetch.mockReturnValueOnce(okJson({ uid: 'xyz', ...payload }))
    const result = await api.simulations.create(payload as any)
    expect(result.uid).toBe('xyz')
  })

  it('throws on non-2xx', async () => {
    mockFetch.mockReturnValueOnce(Promise.resolve({ ok: false, status: 404, statusText: 'Not found', text: () => Promise.resolve('Not found') }))
    await expect(api.simulations.get('bad')).rejects.toThrow('API 404')
  })
})

describe('api.presets', () => {
  it('fetches preset locations', async () => {
    mockFetch.mockReturnValueOnce(okJson([{ name: 'Tohoku', lat: 38.3, lon: 142.4, magnitude: 9.0, direction: 180 }]))
    const presets = await api.presets.locations()
    expect(presets[0].name).toBe('Tohoku')
  })
})
