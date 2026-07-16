export function inheritEventLifecycle(newsList, eventList) {
  const newsItems = Array.isArray(newsList) ? newsList : []
  const events = Array.isArray(eventList) ? eventList : []
  const lifecycleByEventId = new Map(
    events
      .filter((event) => event?.id !== null && event?.id !== undefined)
      .map((event) => [String(event.id), event.lifecycle || '']),
  )

  return newsItems.map((news) => ({
    ...news,
    lifecycle: lifecycleByEventId.get(String(news?.eventId ?? '')) || '',
  }))
}
