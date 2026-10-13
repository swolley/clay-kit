import { test } from 'node:test'
import assert from 'node:assert/strict'

import { barWidth, escapeXml, pillBar, tierFill, tilePill } from '../../plugins/factory/hooks/svg.ts'

const bar = (over: Record<string, unknown> = {}) =>
  pillBar({ label: 'Tasks 1/4', done: 1, total: 4, width: 200, fill: '#2a8f5f', track: '#343a48', ...over })

test('escapeXml neutralizes markup characters', () => {
  assert.equal(escapeXml(`a<b>&"c'`), 'a&lt;b&gt;&amp;&quot;c&apos;')
})

test('pillBar is a self-contained svg with rounded ends and the label as text', () => {
  const s = bar()
  assert.ok(s.startsWith('<svg') && s.endsWith('</svg>'))
  assert.match(s, /rx="10"/)
  assert.ok(s.includes('>Tasks 1/4</text>'))
  assert.ok(s.length < 131072)
})

test('pillBar never lets a label inject markup', () => {
  const s = bar({ label: '<script>alert(1)</script> & <img onerror=x>' })
  assert.ok(!s.includes('<script') && !s.includes('<img'))
  assert.ok(s.includes('&lt;script&gt;'))
})

test('pillBar fills in proportion, and draws no fill for zero', () => {
  assert.match(bar(), /class="fill"[^>]*width="50"/)
  assert.ok(!bar({ done: 0 }).includes('class="fill"'))
  assert.match(bar({ done: 4 }), /class="fill"[^>]*width="200"/)
  assert.match(bar({ done: 9 }), /class="fill"[^>]*width="200"/)
  assert.ok(!bar({ total: 0 }).includes('class="fill"'))
})

test('barWidth grows with the label and has a floor', () => {
  assert.equal(barWidth('x'), 150)
  assert.ok(barWidth('a much longer label for the bar to hold') > barWidth('short label here'))
})

test('tierFill gives each tier a dark enough hex fill for white text', () => {
  const fills = ['light', 'medium', 'careful', 'heavy', 'fable'].map(tierFill)
  assert.equal(new Set(fills).size, 5)
  assert.ok(fills.every(c => /^#[0-9a-f]{6}$/i.test(c)))
  assert.equal(tierFill('nope'), tierFill('medium'))
})

test('tilePill draws a rounded tile with its label and value escaped', () => {
  const s = tilePill({ label: 'Waiting', value: '2 <b>', bg: '#1b2029', border: '#343a48' })
  assert.ok(s.startsWith('<svg') && s.includes('>Waiting</text>') && s.includes('2 &lt;b&gt;'))
  assert.match(s, /rx="8"/)
})

test('pillBar cuts a label that does not fit the width with an ellipsis', () => {
  const s = pillBar({ label: 'a very long label that cannot possibly fit in this bar', done: 1, total: 2, width: 120, fill: '#2a8f5f', track: '#343a48' })
  assert.ok(s.includes('…</text>'))
  assert.ok(!s.includes('possibly fit'))
})
