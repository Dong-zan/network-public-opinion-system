import test from 'node:test'
import assert from 'node:assert/strict'

import { inheritEventLifecycle } from '../src/utils/eventLifecycle.js'

test('新闻生命周期统一继承所属事件生命周期', () => {
  const newsList = [
    { id: '101', eventId: '1', lifecycle: '萌芽期' },
    { id: '102', eventId: '2', lifecycle: '高潮期' },
    { id: '103', eventId: '', lifecycle: '成长期' },
  ]
  const events = [
    { id: '1', lifecycle: '衰退期' },
    { id: '2', lifecycle: '成长期' },
  ]

  assert.deepEqual(
    inheritEventLifecycle(newsList, events).map((news) => news.lifecycle),
    ['衰退期', '成长期', ''],
  )
})
