import test from 'node:test'
import assert from 'node:assert/strict'

import {
  classifyEventKeyword,
  isMeaningfulEventKeyword,
  prepareEventKeywords,
} from '../src/utils/eventKeywords.js'

test('filters numbers, single characters, time words, and generic news words', () => {
  for (const keyword of ['64', '19.5%', '人', '今日', '2026年', '7月16日', '北京时间', '比赛', '球员', '视频', '新闻', '记者']) {
    assert.equal(isMeaningfulEventKeyword(keyword), false, keyword)
  }
  assert.equal(isMeaningfulEventKeyword('裁判判罚'), true)
})

test('classifies valuable event keywords', () => {
  assert.equal(classifyEventKeyword('梅西'), 'entities')
  assert.equal(classifyEventKeyword('国际足联'), 'entities')
  assert.equal(classifyEventKeyword('纪律调查'), 'actions')
  assert.equal(classifyEventKeyword('黑哨争议'), 'attention')
  assert.equal(classifyEventKeyword('阿根廷'), 'entities')
  assert.equal(classifyEventKeyword('世界杯'), 'entities')
})

test('deduplicates keywords and applies the total display limit before grouping', () => {
  const source = [
    '64', '梅西', '阿根廷', '纪律调查', '黑哨争议', '梅西',
    ...Array.from({ length: 20 }, (_, index) => `讨论点${index + 1}`),
  ]
  const result = prepareEventKeywords(source, 15)
  const visible = result.groups.flatMap((group) => group.keywords)

  assert.equal(result.total, 24)
  assert.equal(visible.length, 15)
  assert.equal(result.hasMore, true)
  assert.equal(visible.filter((keyword) => keyword === '梅西').length, 1)
})
