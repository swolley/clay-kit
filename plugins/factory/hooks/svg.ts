// Pure builders for the vector pieces of the progress UI: rounded bars and tiles.
// The strings are SVG documents; every piece of text that comes from a file is escaped.

const FONT = 'system-ui, -apple-system, Segoe UI, sans-serif'

export function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

// Fills dark enough for white text, one per tier.
const TIER_FILLS: Record<string, string> = { light: '#2a8f5f', medium: '#3763d1', careful: '#a87415', heavy: '#c4473c', fable: '#8a4fd1' }

export function tierFill(tier: string): string {
  return TIER_FILLS[tier] ?? TIER_FILLS.medium!
}

// A width in CSS pixels that fits the label at the bar's font size.
export function barWidth(label: string, min = 150): number {
  return Math.max(min, Math.ceil(label.length * 7 + 24))
}

export type PillBar = {
  label: string
  done: number
  total: number
  width: number
  height?: number
  fill: string
  track: string
}

// A fully rounded bar: a track, a fill clipped to the track's shape, and the label as white text on top.
export function pillBar(o: PillBar): string {
  const h = o.height ?? 20
  const room = Math.max(1, Math.floor((o.width - h) / 6.8))
  const label = o.label.length > room ? `${o.label.slice(0, Math.max(0, room - 1))}…` : o.label
  const r = h / 2
  const filled = o.total <= 0 ? 0 : Math.min(o.width, Math.max(0, Math.round((o.width * o.done) / o.total)))
  const fill =
    filled > 0 ? `<rect class="fill" x="0" y="0" width="${filled}" height="${h}" fill="${o.fill}" clip-path="url(#shape)"/>` : ''
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${o.width}" height="${h}" viewBox="0 0 ${o.width} ${h}">` +
    `<defs><clipPath id="shape"><rect width="${o.width}" height="${h}" rx="${r}"/></clipPath></defs>` +
    `<rect width="${o.width}" height="${h}" rx="${r}" fill="${o.track}"/>${fill}` +
    `<text x="${r}" y="${r}" dominant-baseline="central" font-family="${FONT}" font-size="12" font-weight="600" fill="#ffffff">${escapeXml(label)}</text>` +
    `</svg>`
  )
}

export type TilePill = {
  label: string
  value: string
  width?: number
  height?: number
  valueColor?: string
  bg: string
  border: string
}

// A rounded tile with a small label over a bold value.
export function tilePill(o: TilePill): string {
  const w = o.width ?? 118
  const h = o.height ?? 46
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">` +
    `<rect x="0.5" y="0.5" width="${w - 1}" height="${h - 1}" rx="8" fill="${o.bg}" stroke="${o.border}"/>` +
    `<text x="12" y="17" font-family="${FONT}" font-size="11" fill="#98a1b3">${escapeXml(o.label)}</text>` +
    `<text x="12" y="36" font-family="${FONT}" font-size="15" font-weight="700" fill="${o.valueColor ?? '#e6e9ef'}">${escapeXml(o.value)}</text>` +
    `</svg>`
  )
}
