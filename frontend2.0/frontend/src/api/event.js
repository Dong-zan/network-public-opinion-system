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
  return {
    id: String(item.event_id ?? item.id ?? ''),
    title: item.title ?? '未命名事件',
    heat: Number(item.heat ?? item.heat_score) || 0,
    riskLevel: item.risk_level ?? item.riskLevel ?? '未知',
    lifecycle: item.stage ?? item.lifecycle ?? '未知',
    updatedAt: item.update_time ?? item.updatedAt ?? item.publish_time ?? '--',
    summary: item.summary ?? '后端暂未返回事件摘要。',
    overview: normalizeOverview(item.overview, item),
    timeline: normalizeTimeline(item.timeline),
    trend: normalizeTrend(item.trend ?? item.trend_data),
    trendLabels: normalizeTrendLabels(item.trend_labels ?? item.trendLabels),
    trendHighlights: normalizeTrendHighlights(item.trend_highlights ?? item.trendHighlights),
    sentiment: normalizeSentiment(item.sentiment ?? item),
    keywords: normalizeKeywords(item.keywords),
    platforms: normalizePlatforms(item.platform_distribution ?? item.platforms),
    propagationPath: normalizePropagationPath(item.propagation_path ?? item.propagationPath),
    authenticity: normalizeAuthenticity(item.authenticity),
    propagationAnalysis: normalizePropagationAnalysis(item.propagation_analysis),
    aiReport: normalizeAiReport(item),
  }
}

function normalizeOverview(overview, item) {
  return {
    time: overview?.time ?? item.create_time ?? item.update_time ?? '后端暂未返回时间信息',
    location: overview?.location ?? '后端暂未返回地点信息',
    cause: overview?.cause ?? item.summary ?? '后端暂未返回事件起因',
    persons: overview?.persons ?? '后端暂未返回涉事人物信息',
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
    return `${item.time ?? '--'} ${item.content ?? ''}`.trim()
  })
}

function normalizeTrend(trend) {
  if (Array.isArray(trend) && trend.length > 0) {
    return trend.map((item) => Number(item) || 0)
  }
  return [0, 0, 0, 0, 0, 0, 0]
}

function normalizeTrendLabels(labels) {
  if (Array.isArray(labels) && labels.length > 0) {
    return labels
  }
  return ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
}

function normalizeTrendHighlights(highlights) {
  if (Array.isArray(highlights)) {
    return highlights.map((item) => Number(item) || 0)
  }
  return []
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

function normalizePropagationPath(path) {
  if (!Array.isArray(path)) {
    return []
  }
  return path.map((item) => ({
    stage: item.stage ?? '关键节点',
    label: item.label ?? item.content ?? '后端暂未返回路径说明',
    time: item.time ?? '--',
    newsId: item.news_id ?? item.newsId ?? null,
    source: item.source ?? '',
    url: item.url ?? '',
    confidence: Number(item.confidence ?? 0) || 0,
  }))
}

function normalizeAuthenticity(authenticity) {
  if (!authenticity || typeof authenticity !== 'object') {
    return {
      authenticityLabel: '信息不足',
      confidence: 0,
      reason: '后端暂未返回真实性分析结果。',
      evidence: [],
      warnings: ['后端暂未返回真实性分析结果'],
    }
  }

  return {
    authenticityLabel: authenticity.authenticity_label ?? authenticity.authenticityLabel ?? '信息不足',
    confidence: Number(authenticity.confidence) || 0,
    reason: authenticity.reason ?? '后端暂未返回真实性分析理由。',
    evidence: Array.isArray(authenticity.evidence) ? authenticity.evidence : [],
    warnings: Array.isArray(authenticity.warnings) ? authenticity.warnings : [],
  }
}

function normalizePropagationAnalysis(propagationAnalysis) {
  if (!propagationAnalysis || typeof propagationAnalysis !== 'object') {
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
  if (item.ai_report) {
    return normalizeReportShape(item.ai_report)
  }

  if (item.report && typeof item.report === 'object') {
    return normalizeReportShape(item.report)
  }

  return '后端暂未返回 AI 分析报告。'
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
    trend: report.trend ?? '',
    risk: report.risk ?? '',
    suggestion: report.suggestion ?? '',
    generatedAt: report.generated_at ?? report.generatedAt ?? '',
  }
}
