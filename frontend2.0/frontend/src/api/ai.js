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
      answer: `已收到事件 ${payload.event_id} 的问题：“${payload.question}”。当前为前端 mock 回答；后续接入 5 号 AI 模块后，将由后端根据 event_id 查询完整事件上下文再生成回答。`,
    }
  }

  return request('/api/ai/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
