import test from 'node:test'
import assert from 'node:assert/strict'

import { cleanSummary, cleanTitle } from '../src/utils/textClean.js'

test('去除微博话题标签', () => {
  assert.equal(
    cleanTitle('#郑钦文# 北京时间7月15日，WTA250雅典站...'),
    '北京时间7月15日，WTA250雅典站...',
  )
})

test('去除方头括号标签', () => {
  assert.equal(cleanTitle('【热点】AI产品进入大众消费视野'), 'AI产品进入大众消费视野')
})

test('普通新闻标题保持不变', () => {
  assert.equal(cleanTitle('普通新闻标题'), '普通新闻标题')
})

test('摘要去除媒体格式并限制长度', () => {
  assert.equal(
    cleanSummary('来源：某媒体 热点栏目 自选股 数据中心 行情中心 AI产品进入大众消费视野', 12),
    'AI产品进入大众消费视野',
  )
})
