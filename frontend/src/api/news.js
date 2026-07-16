import { mockEvents } from '../data/mock.js'
import { USE_MOCK, request } from './request.js'

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function fetchNewsList() {
  if (USE_MOCK) {
    await wait(240)
    return buildMockNewsList()
  }

  const response = await request('/api/news')
  const payload = unwrapResponse(response)
  return normalizeNewsCollection(payload)
}

export async function fetchEventNews(eventId) {
  if (!eventId) {
    return []
  }

  if (USE_MOCK) {
    await wait(180)
    return buildMockNewsList().filter((item) => String(item.eventId) === String(eventId))
  }

  const response = await request(`/api/events/${eventId}/news`)
  return normalizeNewsCollection(unwrapResponse(response), { eventId: String(eventId) })
}

function buildMockNewsList() {
  return mockEvents
    .flatMap((event) => {
      const newsList = Array.isArray(event.newsList) ? event.newsList : []
      return newsList
        .map((item, index) =>
          normalizeNewsItem(item, index, {
            eventId: event.id,
            eventTitle: event.title,
            heat: event.heat,
            riskLevel: event.riskLevel,
            lifecycle: event.lifecycle,
            keywords: event.keywords,
            sentiment: event.sentiment,
          }),
        )
        .filter(Boolean)
    })
    .sort(sortNewsByTime)
}

function unwrapResponse(response) {
  if (response && typeof response === 'object' && 'data' in response) {
    return response.data
  }
  return response
}

function normalizeNewsCollection(payload, eventContext = {}) {
  const rawNewsList = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.items)
      ? payload.items
      : payload && typeof payload === 'object'
        ? [payload]
        : []

  return rawNewsList
    .map((item, index) => normalizeNewsItem(item, index, eventContext))
    .filter(Boolean)
    .sort(sortNewsByTime)
}

function normalizeNewsItem(item, index = 0, eventContext = {}) {
  if (!item || typeof item !== 'object') {
    return null
  }

  const newsId = item.news_id ?? item.newsId ?? item.id ?? null
  if (newsId === null || newsId === undefined || newsId === '') {
    return null
  }

  const eventId =
    item.event_id ??
    item.eventId ??
    item.parent_event_id ??
    item.parentEventId ??
    eventContext.eventId ??
    ''
  const summary =
    normalizeMaybeEmptyText(item.summary) ??
    normalizeMaybeEmptyText(item.abstract) ??
    normalizeMaybeEmptyText(item.snippet) ??
    normalizeMaybeEmptyText(item.content) ??
    ''
  const itemKeywords = normalizeKeywordList(item.keywords)
  const summaryKeywords = extractKeywordsFromSummary(summary)
  const contextKeywords = normalizeKeywordList(eventContext.keywords)

  return {
    id: String(newsId),
    eventId: eventId ? String(eventId) : '',
    eventTitle:
      normalizeMaybeEmptyText(item.event_title) ??
      normalizeMaybeEmptyText(item.eventTitle) ??
      normalizeMaybeEmptyText(eventContext.eventTitle) ??
      '',
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
    summary,
    overview: normalizeNewsOverview(item, eventContext),
    keywords:
      itemKeywords.length > 0
        ? itemKeywords
        : summaryKeywords.length > 0
          ? summaryKeywords
          : contextKeywords,
    sentimentDistribution: normalizeSentimentDistribution(
      item.sentiment_distribution ?? item.sentimentDistribution ?? item.sentiment,
      eventContext.sentiment,
    ),
    sentiment:
      normalizeSentimentText(item.sentiment_label ?? item.sentimentLabel ?? item.sentiment) ??
      normalizeSentimentText(eventContext.sentiment) ??
      '',
    trendValues: normalizeTrendValues(item.trend ?? item.trend_data, item.heat ?? item.heat_score ?? eventContext.heat),
    trendLabels: normalizeTrendLabels(item.trend_labels ?? item.trendLabels, item.publish_time ?? item.publishTime ?? item.time),
    trendHighlights: normalizeTrendHighlights(item.trend_highlights ?? item.trendHighlights),
    platforms: normalizeNewsPlatforms(item.platform_distribution ?? item.platforms, item.source ?? item.media),
    heat: normalizeNumericValue(item.heat ?? item.heat_score ?? eventContext.heat),
    riskLevel:
      normalizeMaybeEmptyText(item.risk_level) ??
      normalizeMaybeEmptyText(item.riskLevel) ??
      normalizeMaybeEmptyText(eventContext.riskLevel) ??
      '',
    lifecycle: normalizeMaybeEmptyText(eventContext.lifecycle) ?? '',
  }
}

function normalizeNewsOverview(item, eventContext = {}) {
  const rawOverview = item.overview && typeof item.overview === 'object' ? item.overview : {}

  return {
    time:
      normalizeDateTimeText(rawOverview.time) ??
      normalizeDateTimeText(item.publish_time) ??
      normalizeDateTimeText(item.publishTime) ??
      normalizeDateTimeText(item.time) ??
      null,
    location:
      normalizeMaybeEmptyText(rawOverview.location) ??
      normalizeMaybeEmptyText(rawOverview.place) ??
      normalizeMaybeEmptyText(item.location) ??
      null,
    cause:
      normalizeMaybeEmptyText(rawOverview.cause) ??
      normalizeMaybeEmptyText(rawOverview.reason) ??
      normalizeMaybeEmptyText(item.cause) ??
      null,
    persons: normalizePersons(rawOverview.persons ?? rawOverview.people ?? item.persons),
    source:
      normalizeMaybeEmptyText(item.source) ??
      normalizeMaybeEmptyText(item.media) ??
      null,
    eventTitle:
      normalizeMaybeEmptyText(item.event_title) ??
      normalizeMaybeEmptyText(item.eventTitle) ??
      normalizeMaybeEmptyText(eventContext.eventTitle) ??
      null,
  }
}

function normalizeKeywordList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeMaybeEmptyText(item)).filter(Boolean)
  }

  const text = normalizeMaybeEmptyText(value)
  if (!text) {
    return []
  }

  return text
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function extractKeywordsFromSummary(summary) {
  const keywordMatch = String(summary ?? '').match(/关键词\s*[：:]\s*([^。；;\n]+)/)
  return keywordMatch ? normalizeKeywordList(keywordMatch[1]) : []
}

function normalizeSentimentText(value) {
  if (!value) {
    return null
  }

  if (typeof value === 'string') {
    return normalizeMaybeEmptyText(value)
  }

  if (typeof value === 'object') {
    const positive = Number(value.positive) || 0
    const neutral = Number(value.neutral) || 0
    const negative = Number(value.negative) || 0
    const maxValue = Math.max(positive, neutral, negative)

    if (maxValue === 0) {
      return null
    }
    if (maxValue === positive) {
      return '正面'
    }
    if (maxValue === negative) {
      return '负面'
    }
    return '中性'
  }

  return null
}

function normalizeSentimentDistribution(primaryValue, fallbackValue) {
  const source = primaryValue ?? fallbackValue

  if (source && typeof source === 'object' && !Array.isArray(source)) {
    const positive = Number(source.positive) || 0
    const neutral = Number(source.neutral) || 0
    const negative = Number(source.negative) || 0
    const total = positive + neutral + negative

    if (total > 0) {
      return {
        positive: positive / total,
        neutral: neutral / total,
        negative: negative / total,
      }
    }
  }

  return null
}

function normalizeTrendValues(trend, fallbackHeat) {
  if (Array.isArray(trend) && trend.length > 0) {
    return trend
      .map((item) => {
        if (item && typeof item === 'object') {
          return normalizeNumericValue(
            item.value ?? item.count ?? item.volume ?? item.heat ?? item.num ?? item.total,
          )
        }
        return normalizeNumericValue(item)
      })
      .filter((item) => item !== null)
  }

  const heatValue = normalizeNumericValue(fallbackHeat)
  return heatValue !== null ? [heatValue] : []
}

function normalizeTrendLabels(labels, fallbackTime) {
  if (Array.isArray(labels) && labels.length > 0) {
    return labels.map((item) => normalizeDateTimeText(item) ?? normalizeMaybeEmptyText(item) ?? '')
  }

  const text = normalizeDateTimeText(fallbackTime)
  return text ? [text] : []
}

function normalizeTrendHighlights(highlights) {
  if (Array.isArray(highlights) && highlights.length > 0) {
    return highlights
      .map((item) => Number(item))
      .filter((item) => Number.isFinite(item))
  }

  return [0]
}

function normalizeNewsPlatforms(value, fallbackSource) {
  if (Array.isArray(value) && value.length > 0) {
    return value
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return null
        }

        const name =
          normalizeMaybeEmptyText(item.name) ??
          normalizeMaybeEmptyText(item.platform) ??
          normalizeMaybeEmptyText(item.label)
        const numericValue = normalizeNumericValue(item.value ?? item.count ?? item.percent)

        if (!name || numericValue === null) {
          return null
        }

        return { name, value: numericValue }
      })
      .filter(Boolean)
  }

  const source = normalizeMaybeEmptyText(fallbackSource)
  return source ? [{ name: source, value: 100 }] : []
}

function normalizePersons(value) {
  if (Array.isArray(value)) {
    const persons = value
      .map((item) => normalizeMaybeEmptyText(item))
      .filter(Boolean)
    return persons.length > 0 ? persons.join('、') : null
  }

  return normalizeMaybeEmptyText(value) ?? null
}

function normalizeNumericValue(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
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

function toTimestamp(value) {
  const text = normalizeMaybeEmptyText(value)
  if (!text) {
    return 0
  }

  const normalized = text.replace(' ', 'T')
  const timestamp = Date.parse(normalized)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function sortNewsByTime(left, right) {
  const timeDiff = toTimestamp(right.publishTime) - toTimestamp(left.publishTime)
  if (timeDiff !== 0) {
    return timeDiff
  }

  return String(left.id).localeCompare(String(right.id))
}
