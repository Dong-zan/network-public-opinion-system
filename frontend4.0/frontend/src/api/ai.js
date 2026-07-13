import { USE_MOCK, request } from './request.js'

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function askEventQuestion(payload) {
  if (USE_MOCK) {
    await wait(500)
    return `已收到事件 ${payload.event_id} 的问题：“${payload.question}”。当前为前端 mock 回答；后续接入 AI 模块后，将由后端根据 event_id 查询完整事件上下文再生成回答。`
  }

  const response = await request('/api/ai/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  const result = response?.data ?? response
  if (result && typeof result === 'object' && result.error) {
    throw new Error(result.message || 'AI 问答暂时不可用')
  }

  return result
}

export async function generateAiReport(eventId) {
  if (USE_MOCK) {
    await wait(500)
    return {
      event_id: Number(eventId),
      status: 'success',
    }
  }

  const response = await request(`/api/ai/report/${eventId}`, {
    method: 'POST',
  })

  return response?.data ?? response
}

export async function fetchAiReport(eventId) {
  if (USE_MOCK) {
    await wait(300)
    return {
      event_id: Number(eventId),
      report: {
        summary: '这是用于前端演示的 mock AI 报告摘要。',
        overview: {
          time: '近期',
          location: '网络平台',
          cause: '舆情信息快速传播引发关注',
          persons: '相关当事方',
        },
        trend_analysis: '当前热度仍处在波动阶段，短期内仍需持续跟踪舆情扩散情况。',
        risk_analysis: '需关注情绪放大、次生传播以及不实信息混杂带来的风险。',
        suggestions: ['持续补充权威信源', '及时更新事件时间线', '重点监测负面情绪变化'],
        limitations: ['当前内容仅为 mock 数据演示'],
      },
    }
  }

  const response = await request(`/api/ai/report/${eventId}`)
  return response?.data ?? response
}

export async function verifyNews(payload) {
  if (USE_MOCK) {
    await wait(400)
    return {
      event_id: Number(payload.event_id),
      news_id: Number(payload.news_id),
      authenticity_label: '基本可信',
      confidence: 0.76,
      reason: 'mock 数据下未接入真实核验结果。',
      evidence: [],
      warnings: [],
    }
  }

  const response = await request('/api/ai/verify', {
    method: 'POST',
    body: JSON.stringify(payload),
  })

  return response?.data ?? response
}

export async function fetchVerifyResult(eventId, newsId) {
  if (USE_MOCK) {
    await wait(300)
    return {
      event_id: Number(eventId),
      news_id: Number(newsId),
      authenticity_label: '基本可信',
      confidence: 0.76,
      reason: 'mock 数据下未接入真实核验结果。',
      evidence: [],
      warnings: [],
    }
  }

  const response = await request(`/api/ai/verify/${eventId}/${newsId}`)
  return response?.data ?? response
}
