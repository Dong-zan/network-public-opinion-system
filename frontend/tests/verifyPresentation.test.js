import test from 'node:test'
import assert from 'node:assert/strict'

import {
  aggregateEvidenceSources,
  buildAuthenticityPresentation,
  normalizeSourceStatistics,
  normalizeVerifyMetric,
  toPublicOpinionText,
} from '../src/utils/verifyPresentation.js'

test('normalizes the dual verification metrics', () => {
  assert.deepEqual(normalizeVerifyMetric({ level: 'medium', score: 60, explanation: '未发现冲突' }), {
    level: 'medium',
    label: '中',
    explanation: '未发现冲突',
    score: 60,
    factors: {},
  })
})

test('high authenticity prioritizes coverage and moves negative caveats into scope notes', () => {
  const presentation = buildAuthenticityPresentation({
    authenticityAssessment: normalizeVerifyMetric({
      level: 'high',
      label: '高',
      explanation: '当前可信度较高。',
      factors: { source_count: 3, multi_source_consistency: 'consistent' },
    }),
    reasons: ['现有证据不足，无法确认部分信息。', '新华社材料支持核心事实。'],
    evidenceCards: [
      { source: '新华社', stanceKey: 'supports' },
      { source: '央视新闻', stanceKey: 'supports' },
    ],
    sourceStatistics: [{ type: 'news_media', label: '新闻媒体', count: 3 }],
    uncertainties: ['本次核验未联网检索。'],
  })

  assert.equal(presentation.summary, '当前材料包含多个来源，不同来源对核心事实描述基本一致，暂未发现明显矛盾。')
  assert.match(presentation.reasons[0], /支持/)
  assert.equal(presentation.reasons.some((item) => /证据不足|无法确认/.test(item)), false)
  assert.equal(presentation.scopeNotes.some((item) => /证据不足/.test(item)), true)
})

test('medium and low authenticity keep risk reasons prominent', () => {
  const presentation = buildAuthenticityPresentation({
    authenticityAssessment: normalizeVerifyMetric({ level: 'low', label: '低' }),
    reasons: ['不同来源存在冲突，需要进一步确认。'],
    evidenceCards: [],
    sourceStatistics: [],
    uncertainties: [],
  })

  assert.deepEqual(presentation.reasons, ['不同来源存在冲突，需要进一步确认。'])
  assert.deepEqual(presentation.scopeNotes, [])
})

test('normalizes aggregated source statistics', () => {
  assert.deepEqual(
    normalizeSourceStatistics([
      { type: 'weibo', label: '微博', count: 20 },
      { type: 'news_media', label: '新闻媒体', count: 3 },
    ]),
    [
      { type: 'weibo', label: '微博', count: 20 },
      { type: 'news_media', label: '新闻媒体', count: 3 },
    ],
  )
})

test('legacy evidence is aggregated instead of expanded as source statistics', () => {
  assert.deepEqual(
    aggregateEvidenceSources([{ source: '微博' }, { source: '微博' }, { source: '新华社' }]),
    [
      { type: '', label: '微博', count: 2 },
      { type: '', label: '新华社', count: 1 },
    ],
  )
})

test('uses public-opinion wording for legacy fact-check text', () => {
  assert.equal(
    toPublicOpinionText('现有证据不足，无法确认目标主张，暂不可核验。'),
    '现有信息有待补充，事件信息仍待补充，暂缺分析条件。',
  )
})
