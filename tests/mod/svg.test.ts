import { test } from 'node:test'
import assert from 'node:assert/strict'

import { barWidth, escapeXml, pillBar, slimBar, tilePill } from '../../plugins/factory/hooks/svg.ts'

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


test('slimBar is a thin rounded bar with no text', () => {
  const s = slimBar({ done: 1, total: 4, width: 200, fill: '#e0a526', track: '#343a48' })
  assert.ok(s.startsWith('<svg') && s.endsWith('</svg>'))
  assert.ok(!s.includes('<text'))
  assert.match(s, /height="4"/)
  assert.match(s, /rx="2"/)
  assert.match(s, /class="fill"[^>]*width="50"/)
})

test('slimBar draws no fill for zero and a full fill when done', () => {
  assert.ok(!slimBar({ done: 0, total: 4, width: 200, fill: '#e0a526', track: '#343a48' }).includes('class="fill"'))
  assert.match(slimBar({ done: 9, total: 4, width: 200, fill: '#e0a526', track: '#343a48' }), /class="fill"[^>]*width="200"/)
})
