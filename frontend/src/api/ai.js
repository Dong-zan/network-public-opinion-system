import { USE_MOCK, request } from './request.js'

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function askEventQuestion(payload) {
  if (USE_MOCK) {
    await wait(500)
    return {
      answer: `根据当前事件《${payload.title}》的摘要，系统初步判断：${payload.summary}。如果后面接入大模型，这里会结合完整事件数据和你的问题“${payload.question}”生成更细的回答。`,
    }
  }

  return request('/api/ai/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
