function normalizeTagList(list) {
  return Array.from(
    new Set(
      (Array.isArray(list) ? list : [])
        .map((item) => String(item ?? '').trim())
        .filter(Boolean),
    ),
  )
}

function normalizePreferenceText(value) {
  return String(value ?? '').trim().toLocaleLowerCase()
}

function matchesPreferenceFilters(keywordText, platformText, keywordFilters, platformFilters) {
  const matchesKeywords =
    keywordFilters.length === 0 || keywordFilters.some((keyword) => keywordText.includes(keyword))
  const matchesPlatforms =
    platformFilters.length === 0 || platformFilters.some((platform) => platformText.includes(platform))

  return matchesKeywords && matchesPlatforms
}

function getNewsPreferenceText(news) {
  return normalizePreferenceText([
    news?.title,
    news?.summary,
    news?.content,
    news?.eventTitle,
    ...(Array.isArray(news?.keywords) ? news.keywords : []),
  ].join(' '))
}

function getNewsPlatformText(news) {
  return normalizePreferenceText([
    news?.source,
    ...(Array.isArray(news?.platforms) ? news.platforms.map((item) => item?.name) : []),
  ].join(' '))
}

function getEventPreferenceText(event) {
  return normalizePreferenceText([
    event?.title,
    event?.summary,
    ...(Array.isArray(event?.keywords) ? event.keywords : []),
  ].join(' '))
}

function getEventPlatformText(event) {
  return normalizePreferenceText(
    (Array.isArray(event?.platforms) ? event.platforms : []).map((item) => item?.name).join(' '),
  )
}

function resolveNewsEventId(news, events) {
  if (news?.eventId) {
    return String(news.eventId)
  }

  const matchedByTitle = news?.eventTitle
    ? events.find((item) => item.title === news.eventTitle)
    : null
  if (matchedByTitle?.id) {
    return String(matchedByTitle.id)
  }

  const matchedByNews = events.find((event) =>
    Array.isArray(event.newsList) &&
    event.newsList.some((item) => {
      const sameId = item.id && news?.id && String(item.id) === String(news.id)
      const sameTitle = item.title && news?.title && item.title === news.title
      const sameTime =
        item.publishTime &&
        news?.publishTime &&
        String(item.publishTime) === String(news.publishTime)

      return sameId || (sameTitle && sameTime)
    }),
  )

  return matchedByNews?.id ? String(matchedByNews.id) : ''
}

export function filterBoardContent(events, newsList, profile) {
  const baseEvents = Array.isArray(events) ? events : []
  const baseNewsList = Array.isArray(newsList) ? newsList : []
  const keywordFilters = normalizeTagList(profile?.keywords).map(normalizePreferenceText)
  const platformFilters = normalizeTagList(profile?.platforms).map(normalizePreferenceText)

  if (profile?.filterEnabled !== true || (keywordFilters.length === 0 && platformFilters.length === 0)) {
    return { events: baseEvents, newsList: baseNewsList }
  }

  const isNewsVisible = (news) =>
    matchesPreferenceFilters(
      getNewsPreferenceText(news),
      getNewsPlatformText(news),
      keywordFilters,
      platformFilters,
    )

  const filteredNewsList = baseNewsList.filter(isNewsVisible)
  const filteredEvents = baseEvents.filter((event) => {
    const relatedNews = baseNewsList.filter(
      (news) => String(resolveNewsEventId(news, baseEvents)) === String(event.id),
    )
    const keywordText = [
      getEventPreferenceText(event),
      ...relatedNews.map(getNewsPreferenceText),
    ].join(' ')
    const platformText = [
      getEventPlatformText(event),
      ...relatedNews.map(getNewsPlatformText),
    ].join(' ')

    return matchesPreferenceFilters(keywordText, platformText, keywordFilters, platformFilters)
  })

  return { events: filteredEvents, newsList: filteredNewsList }
}
