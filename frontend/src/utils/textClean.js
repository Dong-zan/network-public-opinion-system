const TITLE_MAX_LENGTH = 60
const SUMMARY_MAX_LENGTH = 180

const TOPIC_PATTERN = /#[^#\r\n]{1,80}#/g
const LABEL_PATTERN = /【[^】\r\n]{1,40}】/g
const BRACKET_LABEL_PATTERN = /\[[^\]\r\n]{1,40}\]/g
const ATTRIBUTION_PREFIX_PATTERN = /^(?:(?:来源|记者|编辑|作者|通讯员|供稿|推广|广告)\s*[:：]\s*[^，。；;|｜\s]{1,30}\s*)+/i
const SOURCE_PREFIX_PATTERN = /^(?:转自|转载自|微博热搜|新浪新闻|央视新闻|澎湃新闻|人民网|新华网)\s*(?:[:：|｜-]\s*)+/i
const SUMMARY_FORMAT_PATTERN = /(?:热点栏目|自选股|数据中心|行情中心)\s*(?:[:：|｜-]\s*)?/gi

function normalizeDisplayText(text) {
  return String(text ?? '')
    .replace(TOPIC_PATTERN, ' ')
    .replace(LABEL_PATTERN, ' ')
    .replace(BRACKET_LABEL_PATTERN, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function removeLeadingPrefixes(text) {
  let cleanedText = text
  let previousText = ''

  while (cleanedText && cleanedText !== previousText) {
    previousText = cleanedText
    cleanedText = cleanedText
      .replace(ATTRIBUTION_PREFIX_PATTERN, '')
      .replace(SOURCE_PREFIX_PATTERN, '')
      .trim()
  }

  return cleanedText
}

function truncateText(text, maxLength) {
  const safeMaxLength = Number.isFinite(maxLength) ? Math.max(1, Math.floor(maxLength)) : text.length
  return text.length > safeMaxLength ? `${text.slice(0, safeMaxLength)}…` : text
}

export function cleanTitle(text, maxLength = TITLE_MAX_LENGTH) {
  const cleanedTitle = removeLeadingPrefixes(normalizeDisplayText(text))
  return truncateText(cleanedTitle, maxLength)
}

export function cleanSummary(text, maxLength = SUMMARY_MAX_LENGTH) {
  const cleanedSummary = removeLeadingPrefixes(
    normalizeDisplayText(text).replace(SUMMARY_FORMAT_PATTERN, ' ').replace(/\s+/g, ' ').trim(),
  )
  return truncateText(cleanedSummary, maxLength)
}
