import { useEffect, useState } from 'react'
import { askEventQuestion } from '../api/ai.js'

function AiQuestionCard({ event }) {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    setQuestion('')
    setMessages([
      {
        role: 'assistant',
        content: `你可以围绕“${event.title}”提问，例如：这个事件当前的风险点是什么？`,
      },
    ])
  }, [event.id, event.title])

  async function handleSubmit(eventObject) {
    eventObject.preventDefault()
    const content = question.trim()
    if (!content) {
      return
    }

    const nextMessages = [...messages, { role: 'user', content }]
    setMessages(nextMessages)
    setQuestion('')
    setAsking(true)

    try {
      const response = await askEventQuestion({
        eventId: event.id,
        title: event.title,
        summary: event.summary,
        question: content,
      })
      setMessages([...nextMessages, { role: 'assistant', content: response.answer }])
    } catch (error) {
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: error.message || '智能问答暂时不可用。' },
      ])
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="card wide-card qa-card">
      <div className="section-head">
        <h3>智能问答</h3>
        <span>后续可接入大模型</span>
      </div>
      <div className="qa-messages">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`qa-bubble ${message.role}`}>
            <span className="qa-role">{message.role === 'user' ? '你' : 'AI'}</span>
            <p>{message.content}</p>
          </div>
        ))}
      </div>
      <form className="qa-form" onSubmit={handleSubmit}>
        <textarea
          rows="3"
          value={question}
          onChange={(changeEvent) => setQuestion(changeEvent.target.value)}
          placeholder="例如：这个事件的主要风险点是什么？舆情还会继续升温吗？"
        />
        <button type="submit" className="submit-button" disabled={asking}>
          {asking ? '正在思考...' : '发送问题'}
        </button>
      </form>
    </div>
  )
}

export default AiQuestionCard
