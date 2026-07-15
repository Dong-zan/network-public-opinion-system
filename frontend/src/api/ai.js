import { USE_MOCK, request } from './request.js'

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function askEventQuestion(payload) {
  if (USE_MOCK) {
    await wait(500)
    const target = payload.news_id ? `新闻 ${payload.news_id}` : `事件 ${payload.event_id}`
    return `已收到${target}的问题：“${payload.question}”。当前为前端 mock 回答；后续接入 AI 模块后，将由后端根据对应 ID 查询上下文再生成回答。`
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
      display_result: buildMockVerifyDisplayResult(),
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
      display_result: buildMockVerifyDisplayResult(),
    }
  }

  const response = await request(`/api/ai/verify/${eventId}/${newsId}`)
  return response?.data ?? response
}

function buildMockVerifyDisplayResult() {
  return {
    headline: '示例事故伤亡数字获多来源支持',
    conclusion: '当前输入材料显示，目标新闻中的伤亡数字得到两个独立来源的一致支持。',
    reasons: ['政务发布与新闻媒体的关键信息一致。', '当前样本未发现针对核心事实的直接反驳。'],
    evidence_cards: [
      {
        news_id: 'mock-1',
        source: '示例政务发布',
        source_description: '政务发布',
        quote: '这是用于前端展示的核验证据原文示例，确认目标新闻中的核心数字。',
        stance: 'supports',
        explanation: '该来源与待核验信息的核心表述一致。',
        url: '',
      },
      {
        news_id: 'mock-2',
        source: '示例新闻媒体',
        source_description: '新闻媒体',
        quote: '第二个独立来源确认了相同的核心事实。',
        stance: 'supports',
        explanation: '该来源补充了相关背景信息，且未出现相互矛盾的数字。',
        url: '',
      },
    ],
    uncertainties: ['当前仅为 Mock 数据，实际结论以服务端返回为准。'],
    evidence_score: 0.76,
    risk_score: 0.18,
    assessment_confidence: 0.72,
    relevance_score: 0.9,
    reason_code: 'mock_multi_source_support',
    score_breakdown: { source_coverage: 0.8, content_consistency: 0.74 },
  }
}
