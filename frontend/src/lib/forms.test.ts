import { afterEach, describe, expect, it, vi } from 'vitest'
import { lines, moveItem } from './forms'
import { apiUrl } from './api'

describe('deployment paths and ordered data', () => {
  afterEach(() => vi.unstubAllEnvs())
  it('keeps all API and PDF URLs under the deployment prefix', () => {
    vi.stubEnv('BASE_URL', '/resume/')
    expect(apiUrl('state')).toBe('/resume/api/state')
    expect(apiUrl('/tailored/test/pdf?download=1')).toBe('/resume/api/tailored/test/pdf?download=1')
    vi.stubEnv('BASE_URL', '/tools/resume/')
    expect(apiUrl('state')).toBe('/tools/resume/api/state')
    vi.stubEnv('BASE_URL', '/')
    expect(apiUrl('state')).toBe('/api/state')
  })
  it('moves complete multiline entries without changing the input', () => {
    const points = ['First\ncontinued', 'Second', 'Third']
    expect(moveItem(points, 2, 0)).toEqual(['Third', 'First\ncontinued', 'Second'])
    expect(moveItem(points, 0, 2)).toEqual(['Second', 'Third', 'First\ncontinued'])
    expect(points).toEqual(['First\ncontinued', 'Second', 'Third'])
  })
  it('rejects invalid move boundaries rather than removing an item', () => {
    for (const [from, to] of [[0, -1], [0, 3], [-1, 0], [3, 0], [0.5, 1]]) {
      expect(() => moveItem(['A', 'B', 'C'], from!, to!)).toThrow(RangeError)
    }
  })
  it('splits only the legacy multiline list fields', () => {
    expect(lines(' Python \n\n SQL')).toEqual(['Python', 'SQL'])
  })
})
