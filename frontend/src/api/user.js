import { USE_MOCK, request } from './request.js'

const PROFILE_STORAGE_KEY = 'public-opinion-profile'

export function loadSavedUserProfile() {
  try {
    const storedProfile = localStorage.getItem(PROFILE_STORAGE_KEY)
    return storedProfile ? JSON.parse(storedProfile) : null
  } catch {
    return null
  }
}

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
    return {
      token: 'mock-token',
      user: {
        username: payload.username,
        nickname: payload.username,
      },
    }
  }

  const response = await request('/api/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  return response?.data ?? response
}

export async function registerUser(payload) {
  if (USE_MOCK) {
    await wait(300)
    if (!payload.username || !payload.password || !payload.nickname) {
      throw new Error('请输入用户名、昵称和密码')
    }
    return {
      success: true,
      user: {
        username: payload.username,
        nickname: payload.nickname,
      },
    }
  }

  const response = await request('/api/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  return response?.data ?? response
}

export async function saveUserProfile(payload) {
  if (USE_MOCK) {
    await wait(300)
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(payload))
    return { success: true }
  }

  const response = await request('/api/user/preferences', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  const result = response?.data ?? response
  localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(payload))
  return result
}
