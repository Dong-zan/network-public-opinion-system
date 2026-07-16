const OFFICIAL_PATTERN = /官方|政府|警方|公安|法院|检察院|应急|监管|主管部门|权威发布|通报|回应|声明|辟谣/
const PROGRESS_PATTERN = /后续|进展|进度|处置|救援|调查结果|处理结果|最新情况|恢复|复核|整改|结果公布/
const HEAT_PATTERN = /热搜|热榜|热度|高峰|集中报道|广泛关注|大量转发|引发热议|舆情升温/

export function getTimelineNodeText(node) {
  if (typeof node === 'string') {
    return node
  }

  if (!node || typeof node !== 'object') {
    return ''
  }

  if (typeof node.text === 'string' && node.text.trim()) {
    return node.text
  }

  return [node.time, node.content ?? node.title, node.source ? `来源：${node.source}` : '']
    .filter(Boolean)
    .join(' · ')
}

function toFiniteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function findRelatedNews(node, newsList) {
  if (!node || typeof node !== 'object') {
    return null
  }

  const newsId = node.newsId ?? node.news_id
  if (newsId !== null && newsId !== undefined && newsId !== '') {
    const matchedById = newsList.find((news) => String(news?.id ?? news?.newsId) === String(newsId))
    if (matchedById) {
      return matchedById
    }
  }

  const content = String(node.content ?? node.title ?? '').trim()
  return content ? newsList.find((news) => String(news?.title ?? '').trim() === content) ?? null : null
}

function getNodeHeat(node, newsList) {
  const relatedNews = findRelatedNews(node, newsList)
  const directHeat =
    node && typeof node === 'object'
      ? node.heat ?? node.heatScore ?? node.heat_score ?? node.popularity
      : null
  const heat = toFiniteNumber(directHeat ?? relatedNews?.heat ?? relatedNews?.heatScore)

  if (heat !== null) {
    return heat
  }

  const engagement = ['repostCount', 'commentCount', 'likeCount', 'repost_count', 'comment_count', 'like_count']
    .map((key) => toFiniteNumber(node?.[key] ?? relatedNews?.[key]) ?? 0)
    .reduce((total, value) => total + value, 0)

  return engagement > 0 ? engagement : null
}

function isOfficialNode(node, newsList) {
  const relatedNews = findRelatedNews(node, newsList)
  if (node?.isOfficial === true || node?.is_official === true || relatedNews?.isOfficial === true) {
    return true
  }

  return OFFICIAL_PATTERN.test(
    `${getTimelineNodeText(node)} ${relatedNews?.source ?? ''} ${relatedNews?.accountType ?? ''}`,
  )
}

function addIndex(indexes, index, length) {
  if (Number.isInteger(index) && index >= 0 && index < length) {
    indexes.add(index)
  }
}

/**
 * Selects a compact set of propagation milestones without mutating or discarding
 * the complete timeline. Returned nodes remain in their original timeline order.
 */
export function selectKeyTimelineNodes(timeline, newsList = [], limit = 5) {
  const nodes = Array.isArray(timeline) ? timeline : []
  const relatedNews = Array.isArray(newsList) ? newsList : []

  if (nodes.length <= limit) {
    return nodes
  }

  const selectedIndexes = new Set()

  // 首次报道
  addIndex(selectedIndexes, 0, nodes.length)

  // 热度最高节点。优先使用接口/新闻列表中的热度或互动量，否则识别热榜等语义。
  const rankedByHeat = nodes
    .map((node, index) => ({ index, heat: getNodeHeat(node, relatedNews) }))
    .filter((item) => item.heat !== null)
    .sort((left, right) => right.heat - left.heat || left.index - right.index)
  const heatValues = rankedByHeat.map((item) => item.heat)
  const hasDistinctHeatSignal = heatValues.length > 0 && Math.max(...heatValues) > Math.min(...heatValues)
  const heatSemanticIndex = nodes.findIndex(
    (node, index) => !selectedIndexes.has(index) && HEAT_PATTERN.test(getTimelineNodeText(node)),
  )
  const hottestIndex =
    (hasDistinctHeatSignal
      ? rankedByHeat.find((item) => !selectedIndexes.has(item.index))?.index
      : heatSemanticIndex) ??
    rankedByHeat.find((item) => !selectedIndexes.has(item.index))?.index
  addIndex(selectedIndexes, hottestIndex, nodes.length)

  // 官方回应
  addIndex(
    selectedIndexes,
    nodes.findIndex((node, index) => !selectedIndexes.has(index) && isOfficialNode(node, relatedNews)),
    nodes.length,
  )

  // 后续进展优先取时间更晚的匹配节点。
  let progressIndex = -1
  for (let index = nodes.length - 1; index >= 0; index -= 1) {
    if (!selectedIndexes.has(index) && PROGRESS_PATTERN.test(getTimelineNodeText(nodes[index]))) {
      progressIndex = index
      break
    }
  }
  addIndex(selectedIndexes, progressIndex, nodes.length)

  // 最新报道
  addIndex(selectedIndexes, nodes.length - 1, nodes.length)

  // 某类节点缺失或角色重叠时，从全程均匀补足，仍确保默认恰好展示 limit 个。
  const fallbackIndexes = Array.from({ length: limit }, (_, index) =>
    Math.round((index * (nodes.length - 1)) / (limit - 1)),
  )
  for (const index of [...fallbackIndexes, ...nodes.map((_, nodeIndex) => nodeIndex)]) {
    if (selectedIndexes.size >= limit) {
      break
    }
    addIndex(selectedIndexes, index, nodes.length)
  }

  return [...selectedIndexes]
    .sort((left, right) => left - right)
    .slice(0, limit)
    .map((index) => nodes[index])
}
