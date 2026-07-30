import { describe, expect, it } from 'vitest'
import { LatestRequestGuard } from './asyncRequest'

describe('LatestRequestGuard', () => {
  it('accepts only the latest request for the active context', () => {
    const guard = new LatestRequestGuard()
    const first = guard.begin('stores:A1:CS100001')
    const second = guard.begin('stores:B1:CS100001')

    expect(guard.isCurrent(first)).toBe(false)
    expect(guard.isCurrent(second)).toBe(true)
    expect(guard.isLatest(second)).toBe(true)
  })

  it('invalidates an in-flight request even if the same context is opened again', () => {
    const guard = new LatestRequestGuard()
    const oldRequest = guard.begin('finance:A1:listing-1')
    guard.invalidate()
    const currentRequest = guard.begin('finance:A1:listing-1')

    expect(guard.isCurrent(oldRequest)).toBe(false)
    expect(guard.isLatest(oldRequest)).toBe(false)
    expect(guard.isCurrent(currentRequest)).toBe(true)
  })

  it('rejects an old response after leaving and reopening the same context', () => {
    const guard = new LatestRequestGuard()
    const oldRequest = guard.begin('stores:A1:CS100001')
    guard.activate('stores:B1:CS100001')
    guard.activate('stores:A1:CS100001')

    expect(guard.isLatest(oldRequest)).toBe(true)
    expect(guard.isCurrent(oldRequest)).toBe(false)
  })
})
