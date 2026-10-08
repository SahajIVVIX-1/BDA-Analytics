import { describe, expect, it } from 'vitest'
import { fmtBytes, fmtCompact, fmtInt, fmtPct, fmtSigned, langName } from '../utils/format'
import { toQuery } from '../services/api'
import { colorMap } from '../charts/common'

describe('formatters', () => {
  it('formats numbers and handles missing values', () => {
    expect(fmtCompact(2944814)).toBe('2.9M')
    expect(fmtInt(1234.6)).toBe('1,235')
    expect(fmtPct(16.78)).toBe('16.8%')
    expect(fmtSigned(5)).toBe('+5.0')
    expect(fmtSigned(-0.095, 3)).toBe('-0.095')
    expect(fmtBytes(5 * 1024 * 1024)).toBe('5.0 MB')
    for (const f of [fmtCompact, fmtInt, fmtPct, fmtSigned]) expect(f(null)).toBe('–')
  })
  it('maps language codes', () => {
    expect(langName('ru')).toBe('Russian')
    expect(langName('xx')).toBe('xx')
  })
})

describe('toQuery', () => {
  it('drops empty values', () => {
    expect(toQuery({ a: 1, b: '', c: undefined, d: null, e: false, f: 'x y' })).toBe('?a=1&f=x+y')
    expect(toQuery({})).toBe('')
  })
})

describe('colorMap', () => {
  it('assigns fixed-order colours and folds extras into a neutral colour', () => {
    const keys = Array.from({ length: 10 }, (_, i) => `k${i}`)
    const m = colorMap(keys)
    expect(m.k0).toBe('var(--s1)')
    expect(m.k7).toBe('var(--s8)')
    expect(m.k9).toBe('var(--ink-muted)')
  })
})
