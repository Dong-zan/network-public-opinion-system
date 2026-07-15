const RAW_API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim()
const API_BASE_URL = import.meta.env.DEV ? '' : RAW_API_BASE_URL || 'http://127.0.0.1:8000'
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

function extractErrorMessage(payload, fallbackMessage) {
  if (!payload) {
    return fallbackMessage
  }

  if (typeof payload === 'string') {
    return payload.trim() || fallbackMessage
  }

  if (Array.isArray(payload)) {
    const messages = payload
      .map((item) => {
        if (typeof item === 'string') {
          return item
        }
        if (item && typeof item === 'object') {
          return item.msg || item.message || item.error || item.detail || ''
        }
        return ''
      })
      .filter(Boolean)

    return messages.join('；') || fallbackMessage
  }

  if (typeof payload === 'object') {
    if ('detail' in payload) {
      const detailMessage = extractErrorMessage(payload.detail, '')
      if (detailMessage) {
        return detailMessage
      }
    }

    return (
      payload.message ||
      payload.error ||
      payload.msg ||
      fallbackMessage
    )
  }

  return fallbackMessage
}

async function readResponseBody(response) {
  const text = await response.text()
  if (!text) {
    return null
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(text)
    } catch {
      return text
    }
  }

  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  const data = await readResponseBody(response)

  if (!response.ok) {
    throw new Error(extractErrorMessage(data, `接口请求失败（${response.status}）`))
  }

  if (data && typeof data === 'object' && 'code' in data && Number(data.code) !== 200) {
    throw new Error(extractErrorMessage(data, '接口返回异常'))
  }

  return data
}
