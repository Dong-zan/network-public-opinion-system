import test from 'node:test'
import assert from 'node:assert/strict'

import { filterBoardContent } from '../src/utils/boardFilter.js'

function buildEvents(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: String(index + 1),
    title: index === 0 ? '人工智能产业发布新模型' : `普通事件 ${index + 1}`,
    summary: '',
    keywords: index === 0 ? ['人工智能'] : [],
  }))
}

test('无偏好时展示全部164个事件', () => {
  const events = buildEvents(164)
  const result = filterBoardContent(events, [], {
    keywords: [],
    platforms: [],
    filterEnabled: false,
  })

  assert.equal(result.events.length, 164)
  assert.equal(result.events, events)
})

test('已有偏好但未主动开启筛选时仍展示全部事件', () => {
  const events = buildEvents(164)
  const result = filterBoardContent(events, [], {
    keywords: ['人工智能'],
    platforms: [],
    filterEnabled: false,
  })

  assert.equal(result.events.length, 164)
})

test('主动开启关键词筛选后才过滤事件', () => {
  const events = buildEvents(164)
  const result = filterBoardContent(events, [], {
    keywords: ['人工智能'],
    platforms: [],
    filterEnabled: true,
  })

  assert.equal(result.events.length, 1)
  assert.equal(result.events[0].id, '1')
})
