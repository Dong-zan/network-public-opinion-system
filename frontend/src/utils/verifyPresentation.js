const metricLabels = {
  high: '高',
  medium: '中',
  suspicious: '存疑',
  low: '低',
  complete: '完整',
  general: '一般',
  insufficient: '不足',
}

export function normalizeVerifyMetric(value) {
  if (!value || typeof value !== 'object') {
    return null
  }

  const level = String(value.level ?? '').trim().toLowerCase()
  const label = String(value.label ?? metricLabels[level] ?? '').trim()
  const explanation = String(value.explanation ?? '').trim()
  const numericScore = Number(value.score)

  if (!label && !explanation) {
    return null
  }

  return {
    level,
    label,
    explanation,
    score: Number.isFinite(numericScore) ? numericScore : null,
    factors: value.factors && typeof value.factors === 'object' ? { ...value.factors } : {},
  }
}

export function normalizeSourceStatistics(value) {
  if (!Array.isArray(value)) {
    return []
  }

  return value
    .map((item) => {
      if (!item || typeof item !== 'object') {
        return null
      }
      const label = String(item.label ?? item.type ?? '').trim()
      const count = Number(item.count)
      return label && Number.isFinite(count) && count > 0
        ? { type: String(item.type ?? '').trim(), label, count }
        : null
    })
    .filter(Boolean)
}

export function aggregateEvidenceSources(evidenceCards) {
  const counts = new Map()
  for (const card of Array.isArray(evidenceCards) ? evidenceCards : []) {
    const label = String(card?.source ?? '来源待补充').trim() || '来源待补充'
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  return [...counts.entries()].map(([label, count]) => ({ type: '', label, count }))
}

export function toPublicOpinionText(value) {
  return String(value ?? '')
    .replaceAll('事实核验结论', '事件分析结论')
    .replaceAll('无法确认目标主张', '事件信息仍待补充')
    .replaceAll('无法确认该主张', '该事件信息仍待补充')
    .replaceAll('目标主张', '事件信息')
    .replaceAll('该主张', '该事件信息')
    .replaceAll('暂不可核验', '暂缺分析条件')
    .replaceAll('无法核验', '暂缺分析条件')
    .replaceAll('无法确认', '信息仍待补充')
    .replaceAll('证据不足', '信息有待补充')
}

const limitationPattern =
  /无法验证|无法核验|无法确认|不能支持|不足以支持|未得到.{0,8}支持|缺少.{0,8}证据|缺少.{0,8}来源|证据不足|信息不足|信息有待补充|来源单一|进一步确认|暂不可核验|暂缺分析条件|没有其他独立新闻|未联网|模型|限制/

const reasonOrder = [
  /支持|印证|佐证/,
  /来源|媒体|政务|机构/,
  /一致|冲突|矛盾/,
]

export function buildAuthenticityPresentation({
  authenticityAssessment,
  reasons,
  evidenceCards,
  sourceStatistics,
  uncertainties,
}) {
  const assessment = authenticityAssessment ?? null
  const isHigh = assessment?.level === 'high' || assessment?.label === '高'
  const cards = Array.isArray(evidenceCards) ? evidenceCards : []
  const statistics = Array.isArray(sourceStatistics) ? sourceStatistics : []
  const rawReasons = uniqueText(reasons)
  const rawUncertainties = uniqueText(uncertainties)
  const sortedEvidenceCards = [...cards].sort(
    (left, right) => evidenceStanceOrder(left?.stanceKey) - evidenceStanceOrder(right?.stanceKey),
  )

  if (!isHigh) {
    return {
      isHigh: false,
      summary: assessment?.explanation ?? '',
      reasons: sortReasons(rawReasons),
      scopeNotes: rawUncertainties,
      evidenceCards: sortedEvidenceCards,
    }
  }

  const factors = assessment?.factors ?? {}
  const sourceCount = positiveNumber(factors.source_count)
  const supportSources = new Set(
    cards
      .filter((item) => item?.stanceKey === 'supports')
      .map((item) => String(item?.source ?? '').trim())
      .filter(Boolean),
  )
  const hasContradiction = cards.some((item) => item?.stanceKey === 'contradicts')
  const consistency = String(factors.multi_source_consistency ?? '').toLowerCase()
  const positiveReasons = []

  if (supportSources.size > 0) {
    positiveReasons.push(
      `${supportSources.size}个来源的材料对核心事实形成支持。`,
    )
  }
  if (sourceCount > 0) {
    const sourceTypes = statistics.map((item) => item.label).filter(Boolean)
    positiveReasons.push(
      `当前材料覆盖${sourceCount}个来源${sourceTypes.length ? `，包括${sourceTypes.join('、')}` : ''}。`,
    )
  }
  if (!hasContradiction && consistency === 'consistent') {
    positiveReasons.push('不同来源对核心事实的描述基本一致，暂未发现明显冲突。')
  } else if (!hasContradiction) {
    positiveReasons.push('当前展示材料中暂未发现明显冲突。')
  }
  if (supportSources.size >= 2) {
    positiveReasons.push('核心信息已获得多来源交叉印证。')
  }

  const limitationReasons = rawReasons.filter((item) => limitationPattern.test(item))
  const regularReasons = rawReasons.filter((item) => !limitationPattern.test(item))
  const summary = buildHighAuthenticitySummary({
    assessment,
    sourceCount,
    consistency,
    hasContradiction,
  })

  return {
    isHigh: true,
    summary,
    reasons: sortReasons(uniqueText([...positiveReasons, ...regularReasons])),
    scopeNotes: uniqueText([...rawUncertainties, ...limitationReasons]),
    evidenceCards: sortedEvidenceCards,
  }
}

function buildHighAuthenticitySummary({ assessment, sourceCount, consistency, hasContradiction }) {
  if (sourceCount >= 2 && consistency === 'consistent' && !hasContradiction) {
    return '当前材料包含多个来源，不同来源对核心事实描述基本一致，暂未发现明显矛盾。'
  }
  if (sourceCount >= 2 && !hasContradiction) {
    return '当前材料覆盖多个来源，围绕同一事件形成相互补充的信息，暂未发现明显冲突。'
  }
  return assessment?.explanation ?? ''
}

function sortReasons(values) {
  return values
    .map((text, index) => ({ text, index, rank: reasonRank(text) }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .map((item) => item.text)
}

function reasonRank(value) {
  if (limitationPattern.test(value)) {
    return reasonOrder.length + 1
  }
  const matchedIndex = reasonOrder.findIndex((pattern) => pattern.test(value))
  return matchedIndex === -1 ? reasonOrder.length : matchedIndex
}

function evidenceStanceOrder(value) {
  return { supports: 0, related: 1, updates: 2, contradicts: 3 }[value] ?? 4
}

function positiveNumber(value) {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) && numericValue > 0 ? numericValue : 0
}

function uniqueText(values) {
  return [...new Set((Array.isArray(values) ? values : []).map((item) => String(item ?? '').trim()).filter(Boolean))]
}
