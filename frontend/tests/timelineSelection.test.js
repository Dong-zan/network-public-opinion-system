import test from 'node:test'
import assert from 'node:assert/strict'

import { getTimelineNodeText, selectKeyTimelineNodes } from '../src/utils/timelineSelection.js'

test('五个及以下节点全部展示', () => {
  const timeline = ['首次报道', '官方回应', '最新报道']
  assert.deepEqual(selectKeyTimelineNodes(timeline), timeline)
})

test('默认选出首次、最高热度、官方回应、后续进展和最新报道并保持原顺序', () => {
  const timeline = [
    { newsId: '1', text: '首次报道' },
    { newsId: '2', text: '普通跟进' },
    { newsId: '3', text: '话题登上热搜' },
    { newsId: '4', text: '媒体评论' },
    { newsId: '5', text: '官方发布回应声明' },
    { newsId: '6', text: '补充报道' },
    { newsId: '7', text: '事件后续调查结果公布' },
    { newsId: '8', text: '最新报道' },
  ]
  const newsList = timeline.map((node, index) => ({ id: node.newsId, heat: index === 2 ? 99 : index }))

  assert.deepEqual(
    selectKeyTimelineNodes(timeline, newsList).map((node) => node.newsId),
    ['1', '3', '5', '7', '8'],
  )
})

test('关键角色缺失时补足五个节点且不修改完整数据', () => {
  const timeline = Array.from({ length: 9 }, (_, index) => `节点 ${index + 1}`)
  const selected = selectKeyTimelineNodes(timeline)

  assert.equal(selected.length, 5)
  assert.equal(timeline.length, 9)
  assert.equal(selected[0], '节点 1')
  assert.equal(selected.at(-1), '节点 9')
  assert.equal(getTimelineNodeText({ time: '10:00', content: '通报', source: '政府发布' }), '10:00 · 通报 · 来源：政府发布')
})

test('所有新闻热度相同时优先识别热榜语义', () => {
  const timeline = [
    { newsId: '1', text: '首次报道' },
    { newsId: '2', text: '普通跟进' },
    { newsId: '3', text: '话题登上热榜' },
    { newsId: '4', text: '媒体评论' },
    { newsId: '5', text: '官方回应' },
    { newsId: '6', text: '后续调查结果公布' },
    { newsId: '7', text: '最新报道' },
  ]
  const newsList = timeline.map((node) => ({ id: node.newsId, heat: 80 }))

  assert.deepEqual(
    selectKeyTimelineNodes(timeline, newsList).map((node) => node.newsId),
    ['1', '3', '5', '6', '7'],
  )
})
