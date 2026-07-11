import { USE_MOCK, request } from './request.js'

const PROFILE_STORAGE_KEY = 'public-opinion-profile'

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function loginUser(payload) {
  if (USE_MOCK) {
    await wait(300)
    if (!payload.username || !payload.password) {
      throw new Error('请输入用户名和密码')
    }
    return { token: 'mock-token', user: { username: payload.username } }
  }

  return request('/api/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function saveUserProfile(payload) {
  if (USE_MOCK) {
    await wait(300)
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(payload))
    return { success: true }
  }

  return request('/api/user/preferences', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
