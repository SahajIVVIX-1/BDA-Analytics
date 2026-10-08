const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })
const full = new Intl.NumberFormat('en')

export const fmtCompact = (n) => (n === null || n === undefined || Number.isNaN(n) ? '–' : compact.format(n))
export const fmtInt = (n) => (n === null || n === undefined ? '–' : full.format(Math.round(n)))
export const fmtPct = (n, digits = 1) => (n === null || n === undefined ? '–' : `${Number(n).toFixed(digits)}%`)
export const fmtSigned = (n, digits = 1) =>
  n === null || n === undefined ? '–' : `${n > 0 ? '+' : ''}${Number(n).toFixed(digits)}`
export const fmtMs = (n) => (n === null || n === undefined ? '–' : n < 1000 ? `${Math.round(n)} ms` : `${(n / 1000).toFixed(2)} s`)
export const fmtBytes = (b) => {
  if (b === null || b === undefined) return '–'
  const u = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++ }
  return `${b.toFixed(i ? 1 : 0)} ${u[i]}`
}

const dayFmt = new Intl.DateTimeFormat('en', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' })
const monthFmt = new Intl.DateTimeFormat('en', { year: 'numeric', month: 'short', timeZone: 'UTC' })
const dtFmt = new Intl.DateTimeFormat('en', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit',
  minute: '2-digit', timeZone: 'UTC' })

export const fmtDay = (iso) => (iso ? dayFmt.format(new Date(iso)) : '–')
export const fmtMonth = (iso) => (iso ? monthFmt.format(new Date(iso)) : '–')
export const fmtDateTime = (iso) => (iso ? `${dtFmt.format(new Date(iso))} UTC` : '–')
export const tickForGranularity = (g) => (g === 'month' ? fmtMonth : (iso) =>
  new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: '2-digit', timeZone: 'UTC' }).format(new Date(iso)))

export const LANGUAGE_NAMES = {
  en: 'English', ru: 'Russian', de: 'German', uk: 'Ukrainian', it: 'Italian', sr: 'Serbian', uz: 'Uzbek',
  bg: 'Bulgarian', ar: 'Arabic', mk: 'Macedonian', fr: 'French', es: 'Spanish', no: 'Norwegian', fa: 'Farsi',
  nl: 'Dutch', sv: 'Swedish', ro: 'Romanian', ja: 'Japanese', et: 'Estonian', hr: 'Croatian', pt: 'Portuguese',
  pl: 'Polish', fi: 'Finnish', lt: 'Lithuanian', hu: 'Hungarian', tr: 'Turkish', cs: 'Czech', unknown: 'Unknown',
}
export const langName = (code) => LANGUAGE_NAMES[code] || code
