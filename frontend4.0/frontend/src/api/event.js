import { mockEvents } from '../data/mock.js'
import { USE_MOCK, request } from './request.js'

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function fetchEvents() {
  if (USE_MOCK) {
    await wait(300)
    return [...mockEvents]
  }

  const response = await request('/api/events')
  const payload = unwrapResponse(response)
  const eventList = Array.isArray(payload) ? payload : []
  return eventList.map((item) => normalizeEventListItem(item))
}

export async function fetchEventDetail(eventId) {
  if (USE_MOCK) {
    await wait(200)
    const event = mockEvents.find((item) => item.id === eventId)
    if (!event) {
      throw new Error('未找到对应事件')
    }
    return { ...event }
  }

  const response = await request(`/api/events/${eventId}`)
  return normalizeEventDetail(unwrapResponse(response))
}

function unwrapResponse(response) {
  if (response && typeof response === 'object' && 'data' in response) {
    return response.data
  }
  return response
}

function normalizeEventListItem(item) {
  return normalizeEventShape(item)
}

function normalizeEventDetail(item) {
  return normalizeEventShape(item)
}

function normalizeEventShape(item = {}) {
  const rawTimeline = Array.isArray(item.timeline) ? item.timeline : []
  const trendSource = normalizeTrendSource(
    item.trend ?? item.trend_data,
    item.trend_labels ?? item.trendLabels,
    item.trend_highlights ?? item.trendHighlights,
  )

  return {
    id: String(item.event_id ?? item.id ?? ''),
    title: item.title ?? '未命名事件',
    heat: Number(item.heat ?? item.heat_score) || 0,
    riskLevel: item.risk_level ?? item.riskLevel ?? '未知',
    lifecycle: item.stage ?? item.lifecycle ?? '未知',
    updatedAt: normalizeDateTimeText(
      item.update_time ?? item.updatedAt ?? item.publish_time ?? item.create_time ?? '--',
    ),
    summary: item.summary ?? '后端暂未返回事件摘要。',
    overview: normalizeOverview(item.overview, item),
    timeline: normalizeTimeline(rawTimeline),
    trend: trendSource.values,
    trendLabels: trendSource.labels,
    trendHighlights: trendSource.highlights,
    sentiment: normalizeSentiment(item.sentiment ?? item),
    keywords: normalizeKeywords(item.keywords),
    platforms: normalizePlatforms(item.platform_distribution ?? item.platforms),
    newsList: normalizeNewsList(
      item.news_list ?? item.newsList ?? item.articles ?? item.news ?? item.related_news,
      item.propagation_path ?? item.propagationPath,
      rawTimeline,
    ),
    propagationPath: normalizePropagationPath(item.propagation_path ?? item.propagationPath),
    authenticity: normalizeAuthenticity(item.authenticity),
    propagationAnalysis: normalizePropagationAnalysis(item.propagation_analysis),
    aiReportStatus: normalizeAiReportStatus(item),
    aiReport: normalizeAiReport(item),
  }
}

function normalizeOverview(overview, item) {
  const normalizedOverview = overview && typeof overview === 'object' ? overview : {}

  return {
    time:
      normalizeDateTimeText(normalizedOverview.time) ??
      normalizeDateTimeText(item.create_time) ??
      normalizeDateTimeText(item.update_time) ??
      '后端暂未返回时间信息',
    location:
      normalizeMaybeEmptyText(normalizedOverview.location) ??
      normalizeMaybeEmptyText(normalizedOverview.place) ??
      normalizeMaybeEmptyText(item.location) ??
      '后端暂未返回地点信息',
    cause:
      normalizeMaybeEmptyText(normalizedOverview.cause) ??
      normalizeMaybeEmptyText(normalizedOverview.reason) ??
      '后端暂未返回事件起因',
    persons: normalizePersons(
      normalizedOverview.persons ?? normalizedOverview.people ?? item.persons,
    ),
  }
}

function normalizeTimeline(timeline) {
  if (!Array.isArray(timeline)) {
    return []
  }

  return timeline.map((item) => {
    if (typeof item === 'string') {
      return item
    }

    const time = normalizeDateTimeText(item.time)
    const content =
      normalizeMaybeEmptyText(item.content) ??
      normalizeMaybeEmptyText(item.title) ??
      '后端暂未返回时间线内容'
    const source = normalizeMaybeEmptyText(item.source)

    return [time, content, source ? `来源：${source}` : ''].filter(Boolean).join(' · ')
  })
}

function normalizeTrendSource(trend, labels, highlights) {
  const trendList = Array.isArray(trend) ? trend : []
  const fallbackHighlights = normalizeTrendHighlights(highlights)

  if (trendList.length === 0) {
    return {
      values: [],
      labels: normalizeTrendLabels(labels, 0),
      highlights: fallbackHighlights,
    }
  }

  const allObjects = trendList.every((item) => item && typeof item === 'object' && !Array.isArray(item))
  if (allObjects) {
    const normalizedPoints = trendList.map((item, index) => ({
      value: normalizeTrendValue(
        item.value ?? item.count ?? item.volume ?? item.heat ?? item.num ?? item.total,
      ),
      label: normalizeTrendLabel(
        item.time ?? item.label ?? item.date ?? item.datetime ?? item.timestamp ?? item.x,
      ),
      highlighted: Boolean(item.highlight ?? item.is_highlight ?? item.is_key ?? item.key_node),
      index,
    }))

    const derivedHighlights = normalizedPoints
      .filter((item) => item.highlighted)
      .map((item) => item.index)

    const normalizedLabels = normalizedPoints.map((item) => item.label)
    const hasRealLabels = normalizedLabels.some(Boolean)

    return {
      values: normalizedPoints.map((item) => item.value),
      labels: hasRealLabels ? normalizedLabels : normalizeTrendLabels(labels, normalizedPoints.length),
      highlights: Array.from(new Set([...fallbackHighlights, ...derivedHighlights])),
    }
  }

  return {
    values: trendList.map((item) => normalizeTrendValue(item)),
    labels: normalizeTrendLabels(labels, trendList.length),
    highlights: fallbackHighlights,
  }
}

function normalizeTrendValue(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

function normalizeTrendLabel(value) {
  return normalizeDateTimeText(value) ?? normalizeMaybeEmptyText(value) ?? ''
}

function normalizeTrendLabels(labels, expectedLength = 0) {
  if (Array.isArray(labels) && labels.length > 0) {
    return Array.from({ length: expectedLength || labels.length }, (_, index) =>
      normalizeTrendLabel(labels[index]),
    )
  }

  if (expectedLength > 0) {
    return Array.from({ length: expectedLength }, () => '')
  }

  return []
}

function normalizeTrendHighlights(highlights) {
  if (!Array.isArray(highlights)) {
    return []
  }

  return Array.from(
    new Set(
      highlights
        .map((item) => Number(item))
        .filter((item) => Number.isFinite(item)),
    ),
  )
}

function normalizeKeywords(keywords) {
  if (Array.isArray(keywords)) {
    return keywords
  }
  if (typeof keywords === 'string' && keywords.trim()) {
    return keywords
      .split(/[，,、]/)
      .map((item) => item.trim())
      .filter(Boolean)
  }
  return []
}

function normalizePlatforms(platformDistribution) {
  if (Array.isArray(platformDistribution)) {
    return platformDistribution.map((item) => ({
      name: item.name ?? item.platform ?? '未知平台',
      value: Number(item.value ?? item.count) || 0,
    }))
  }

  if (platformDistribution && typeof platformDistribution === 'object') {
    return Object.entries(platformDistribution).map(([name, value]) => ({
      name,
      value: Number(value) || 0,
    }))
  }

  if (typeof platformDistribution === 'string' && platformDistribution.trim()) {
    try {
      const parsed = JSON.parse(platformDistribution)
      return normalizePlatforms(parsed)
    } catch {
      return []
    }
  }

  return []
}

function normalizeNewsList(newsList, propagationPath, timeline) {
  if (Array.isArray(newsList) && newsList.length > 0) {
    return newsList
      .map((item, index) => normalizeNewsItem(item, index))
      .filter(Boolean)
  }

  if (Array.isArray(propagationPath) && propagationPath.length > 0) {
    return propagationPath
      .map((item, index) => {
        const newsId = item.news_id ?? item.newsId ?? null
        if (!newsId) {
          return null
        }

        return normalizeNewsItem(
          {
            news_id: newsId,
            title: item.label ?? item.content ?? `${item.stage ?? '新闻'}相关内容`,
            source: item.source ?? '',
            publish_time: item.time ?? '',
            url: item.url ?? '',
          },
          index,
        )
        })
      .filter(Boolean)
  }

  if (Array.isArray(timeline) && timeline.length > 0) {
    return timeline
      .map((item, index) => {
        if (!item || typeof item !== 'object') {
          return null
        }

        const newsId = item.news_id ?? item.newsId ?? null
        if (!newsId) {
          return null
        }

        return normalizeNewsItem(
          {
            news_id: newsId,
            title: item.title ?? item.content ?? `新闻 ${index + 1}`,
            source: item.source ?? '',
            publish_time: item.time ?? '',
            content: item.content ?? '',
          },
          index,
        )
      })
      .filter(Boolean)
  }

  return []
}

function normalizeNewsItem(item, index = 0) {
  if (!item || typeof item !== 'object') {
    return null
  }

  const newsId = item.news_id ?? item.newsId ?? item.id ?? null
  if (newsId === null || newsId === undefined || newsId === '') {
    return null
  }

  return {
    id: String(newsId),
    title:
      normalizeMaybeEmptyText(item.title) ??
      normalizeMaybeEmptyText(item.headline) ??
      normalizeMaybeEmptyText(item.label) ??
      `新闻 ${index + 1}`,
    source:
      normalizeMaybeEmptyText(item.source) ??
      normalizeMaybeEmptyText(item.media) ??
      '来源待补充',
    publishTime:
      normalizeDateTimeText(item.publish_time) ??
      normalizeDateTimeText(item.publishTime) ??
      normalizeDateTimeText(item.time) ??
      '--',
    url:
      normalizeMaybeEmptyText(item.url) ??
      normalizeMaybeEmptyText(item.link) ??
      '',
    content:
      normalizeMaybeEmptyText(item.content) ??
      normalizeMaybeEmptyText(item.summary) ??
      normalizeMaybeEmptyText(item.snippet) ??
      '',
  }
}

function normalizePropagationPath(path) {
  if (Array.isArray(path) && path.length > 0) {
    return path.map((item) => ({
      stage: item.stage ?? '关键节点',
      label: item.label ?? item.content ?? '后端暂未返回路径说明',
      time: normalizeDateTimeText(item.time) ?? '--',
      newsId: item.news_id ?? item.newsId ?? null,
      source: item.source ?? '',
      url: item.url ?? '',
      confidence: Number(item.confidence ?? 0) || 0,
    }))
  }

  return []
}

function normalizeAuthenticity(authenticity) {
  if (!isMeaningfulObject(authenticity)) {
    return {
      authenticityLabel: '信息不足',
      confidence: null,
      reason: '后端暂未返回真实性分析结果。',
      evidence: [],
      warnings: ['后端暂未返回真实性分析结果'],
    }
  }

  return {
    authenticityLabel: authenticity.authenticity_label ?? authenticity.authenticityLabel ?? '信息不足',
    confidence:
      authenticity.confidence === null || authenticity.confidence === undefined
        ? null
        : Number(authenticity.confidence),
    reason: authenticity.reason ?? '后端暂未返回真实性分析理由。',
    evidence: Array.isArray(authenticity.evidence) ? authenticity.evidence : [],
    warnings: Array.isArray(authenticity.warnings) ? authenticity.warnings : [],
  }
}

function normalizePropagationAnalysis(propagationAnalysis) {
  if (!isMeaningfulObject(propagationAnalysis)) {
    return {
      origin: null,
      keyNodes: [],
      path: [],
      confidence: 0,
      limitations: ['后端暂未返回传播路径分析结果'],
    }
  }

  const keyNodes = propagationAnalysis.key_nodes ?? propagationAnalysis.keyNodes

  return {
    origin: propagationAnalysis.origin ?? null,
    keyNodes: Array.isArray(keyNodes) ? keyNodes : [],
    path: Array.isArray(propagationAnalysis.path) ? propagationAnalysis.path : [],
    confidence: Number(propagationAnalysis.confidence) || 0,
    limitations: Array.isArray(propagationAnalysis.limitations) ? propagationAnalysis.limitations : [],
  }
}

function normalizeSentiment(sentiment) {
  const fallback = { positive: 0, neutral: 0, negative: 0 }
  if (!sentiment || typeof sentiment !== 'object') {
    return fallback
  }

  const positive = Number(sentiment.positive) || 0
  const neutral = Number(sentiment.neutral) || 0
  const negative = Number(sentiment.negative) || 0
  const maxValue = Math.max(positive, neutral, negative)

  if (maxValue <= 1) {
    return { positive, neutral, negative }
  }

  return {
    positive: positive / 100,
    neutral: neutral / 100,
    negative: negative / 100,
  }
}

function normalizeAiReport(item) {
  const status = normalizeAiReportStatus(item)
  if (status === 'failed') {
    return null
  }

  if (typeof item.ai_report === 'string') {
    return normalizeReportShape(item.ai_report)
  }

  if (isMeaningfulObject(item.ai_report)) {
    return normalizeReportShape(item.ai_report)
  }

  if (typeof item.report === 'string') {
    return normalizeReportShape(item.report)
  }

  if (isMeaningfulObject(item.report)) {
    return normalizeReportShape(item.report)
  }

  return '后端暂未返回 AI 分析报告。'
}

function normalizeAiReportStatus(item) {
  const aiReportStatus = normalizeMaybeEmptyText(item.ai_report_status)
  const nestedStatus = isMeaningfulObject(item.ai_report)
    ? normalizeMaybeEmptyText(item.ai_report.status)
    : null
  const reportStatus = normalizeMaybeEmptyText(item.report_status)
  const topLevelStatus = normalizeMaybeEmptyText(item.status)

  return aiReportStatus ?? nestedStatus ?? reportStatus ?? topLevelStatus ?? ''
}

function normalizeReportShape(report) {
  if (typeof report === 'string') {
    return report
  }

  if (!report || typeof report !== 'object') {
    return '后端暂未返回 AI 分析报告。'
  }

  return {
    summary: report.summary ?? '',
    overview: normalizeReportOverview(report.overview),
    trendAnalysis: report.trend_analysis ?? report.trendAnalysis ?? report.trend ?? '',
    riskAnalysis: report.risk_analysis ?? report.riskAnalysis ?? report.risk ?? '',
    suggestions: normalizeReportList(report.suggestions ?? report.suggestion),
    limitations: normalizeReportList(report.limitations),
  }
}

function normalizeReportOverview(value) {
  if (!value || typeof value !== 'object') {
    return {}
  }

  const overview = {}
  const time = normalizeDateTimeText(value.time)
  const location = normalizeMaybeEmptyText(value.location)
  const cause = normalizeMaybeEmptyText(value.cause)
  const persons = normalizeMaybeEmptyText(value.persons)

  if (time) {
    overview.time = time
  }
  if (location) {
    overview.location = location
  }
  if (cause) {
    overview.cause = cause
  }
  if (persons) {
    overview.persons = persons
  }

  return overview
}

function normalizeReportList(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeMaybeEmptyText(item))
      .filter(Boolean)
  }

  const singleValue = normalizeMaybeEmptyText(value)
  return singleValue ? [singleValue] : []
}

function normalizeMaybeEmptyText(value) {
  if (value === null || value === undefined) {
    return null
  }

  const text = String(value).trim()
  if (!text || text === 'None' || text === 'null' || text === 'undefined') {
    return null
  }

  return text
}

function normalizeDateTimeText(value) {
  const text = normalizeMaybeEmptyText(value)
  if (!text) {
    return null
  }

  return text
    .replace('T', ' ')
    .replace(/\.\d+$/, '')
    .replace(/Z$/, '')
    .trim()
}

function normalizePersons(value) {
  if (Array.isArray(value)) {
    const persons = value
      .map((item) => normalizeMaybeEmptyText(item))
      .filter(Boolean)
    return persons.length > 0 ? persons.join('、') : '后端暂未返回涉事人物信息'
  }

  return normalizeMaybeEmptyText(value) ?? '后端暂未返回涉事人物信息'
}

function isMeaningfulObject(value) {
  return Boolean(value) && typeof value === 'object' && Object.keys(value).length > 0
}
