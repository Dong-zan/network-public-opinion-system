const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'

export async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    throw new Error(data?.message || '接口请求失败')
  }

  if (data && typeof data === 'object' && 'code' in data && Number(data.code) !== 200) {
    throw new Error(data?.message || '接口返回异常')
  }

  return data
}
