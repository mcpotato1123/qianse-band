// Reading preferences, save slots and text layout — shared by every page.
// Layout is recomputed at run time so the font size stays stepless (14–30px).

import storage from '@system.storage'

export const SIZE_MIN = 14
export const SIZE_MAX = 30
export const SPEED_MIN = 0
export const SPEED_MAX = 120
export const AUTO_MIN = 0
export const AUTO_MAX = 200
export const MAX_SLOTS = 6

export const DEFAULT_SETTINGS = {
  size: 20,
  speed: 28,
  autoMs: 0,
  fast: false,
  keepOn: true,
  longpress: 'off',
}

// ---------------------------------------------------------------- geometry
// Keep in sync with game.ux CSS (.panel / .name / .ln).
export const PANEL_TOP = 330
export const PANEL_H = 150
export const NAME_TOP = 292
export const TEXT_TOP = 338
export const TEXT_BOX_W = 316
export const TEXT_PAD = 6
export const TEXT_BOX_H = 144
export const MAX_LINES = 6

export function layout(settings) {
  const size = clampInt(settings.size, SIZE_MIN, SIZE_MAX, DEFAULT_SETTINGS.size)
  const lineH = size + 4
  return {
    size: size,
    lineH: lineH,
    cpl: Math.max(4, Math.floor((TEXT_BOX_W - TEXT_PAD) / size)),
    lpp: Math.max(1, Math.min(MAX_LINES, Math.floor(TEXT_BOX_H / lineH))),
  }
}

function clampInt(v, lo, hi, dflt) {
  const n = Math.round(Number(v))
  if (!isFinite(n)) return dflt
  return Math.max(lo, Math.min(hi, n))
}

export function normalizeSettings(raw) {
  const s = Object.assign({}, DEFAULT_SETTINGS, raw || {})
  s.size = clampInt(s.size, SIZE_MIN, SIZE_MAX, DEFAULT_SETTINGS.size)
  s.speed = clampInt(s.speed, SPEED_MIN, SPEED_MAX, DEFAULT_SETTINGS.speed)
  s.autoMs = clampInt(s.autoMs, AUTO_MIN, AUTO_MAX, DEFAULT_SETTINGS.autoMs)
  s.fast = false                       // never restored: it would fast-forward on launch
  s.keepOn = (s.keepOn === undefined || s.keepOn === null) ? DEFAULT_SETTINGS.keepOn : !!s.keepOn
  if (s.longpress === true) s.longpress = 'hide'
  else if (s.longpress === false) s.longpress = 'off'
  else if (s.longpress !== 'hide' && s.longpress !== 'fast' && s.longpress !== 'off') {
    s.longpress = DEFAULT_SETTINGS.longpress
  }
  delete s.auto
  delete s.autoSpeed
  return s
}

export function autoDelay(text, autoMs) {
  const n = String(text || '').replace(/\s/g, '').length
  return Math.max(1200, Math.min(12000, Math.round(700 + n * autoMs)))
}

// ---------------------------------------------------------------- wrapping
// Break after punctuation first, so a comma never starts a line.
const BREAK_AFTER = '，。！？；：、）」』…—'

export function wrapText(text, cpl) {
  const lines = []
  const raws = String(text || '').split('\n')
  for (let i = 0; i < raws.length; i++) {
    let s = raws[i]
    if (s === '') { lines.push(''); continue }
    while (s.length > cpl) {
      let cut = cpl
      const lo = Math.max(2, cpl - 8)
      for (let k = cpl; k > lo; k--) {
        if (BREAK_AFTER.indexOf(s.charAt(k - 1)) >= 0) { cut = k; break }
      }
      lines.push(s.slice(0, cut))
      s = s.slice(cut)
    }
    lines.push(s)
  }
  return lines.length ? lines : ['']
}

export function paginateText(text, cpl, lpp) {
  const lines = wrapText(text, cpl)
  if (!lines.length) return [['']]
  if (lines.length <= lpp) return [lines]
  // 均分：6 行 5 行/页 时给 3+3，而不是 5+1 —— 一句话被拆页时两边长度差不多，
  // 不会出现第二页只剩一个字的尴尬。
  const pages = Math.ceil(lines.length / lpp)
  const per = Math.ceil(lines.length / pages)
  const out = []
  for (let i = 0; i < lines.length; i += per) {
    const chunk = lines.slice(i, i + per)
    const last = out.length ? out[out.length - 1] : null
    if (last && last.length + chunk.length <= lpp) {
      out[out.length - 1] = last.concat(chunk)
    } else {
      out.push(chunk)
    }
  }
  return out
}

// ---------------------------------------------------------------- storage
export function readJSON(key, fallback, done) {
  storage.get({
    key: key,
    default: '',
    success: (v) => {
      if (!v) return done(fallback)
      try { done(JSON.parse(v)) } catch (e) { done(fallback) }
    },
    fail: () => done(fallback),
  })
}

export function writeJSON(key, value, done) {
  storage.set({
    key: key,
    value: JSON.stringify(value),
    success: () => { if (done) done(true) },
    fail: () => { if (done) done(false) },
  })
}

export function loadSettings(done) { readJSON('settings', null, (v) => done(normalizeSettings(v))) }

export function saveSettings(s, done) {
  const t = Object.assign({}, s)
  delete t.fast
  writeJSON('settings', t, done)
}

export function loadSaves(done) { readJSON('saves', [], (v) => done(Array.isArray(v) ? v : [])) }
export function saveSaves(list, done) { writeJSON('saves', list, done) }

export function loadAutoSave(done) { readJSON('autoSave', null, done) }
export function saveAutoSave(data, done) { writeJSON('autoSave', data, done) }

export function loadSeen(done) { readJSON('cgSeen', [], (v) => done(Array.isArray(v) ? v : [])) }
export function saveSeen(list, done) { writeJSON('cgSeen', list, done) }

export function loadCleared(done) { readJSON('cleared', null, (v) => done(!!(v && v.ok))) }
export function markCleared(done) { writeJSON('cleared', { ok: 1, at: Date.now() }, done) }
