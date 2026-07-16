export const NEWS_CONTENT_PREVIEW_LENGTH = 500

export function buildNewsContentPresentation(
  content,
  expanded = false,
  maxLength = NEWS_CONTENT_PREVIEW_LENGTH,
) {
  const fullContent = typeof content === 'string' ? content : ''
  const characters = Array.from(fullContent)
  const isLong = characters.length > maxLength

  return {
    fullContent,
    displayContent: isLong && !expanded ? `${characters.slice(0, maxLength).join('')}…` : fullContent,
    isLong,
  }
}
