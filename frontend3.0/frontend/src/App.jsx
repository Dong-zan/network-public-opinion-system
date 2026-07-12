import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { askEventQuestion } from './api/ai.js'
import { fetchEventDetail, fetchEvents } from './api/event.js'
import { loginUser, saveUserProfile } from './api/user.js'
import { defaultProfile, navItems } from './data/mock.js'

const pageTitles = {
  dashboard: '首页',
  board: '舆情事件看板',
  detail: '事件详情',
  qa: '智能问答',
  profile: '个人中心',
}

const navShortLabels = {
  dashboard: '首',
  board: '板',
  detail: '详',
  qa: '问',
  profile: '我',
}

const keywordSuggestions = ['人工智能', '网络安全', '极端天气', '公共安全', '高校舆情']
const platformSuggestions = ['新闻网站', '微博', '论坛社区', '短视频平台', '开发者社区']

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [activePage, setActivePage] = useState('dashboard')
  const [events, setEvents] = useState([])
  const [selectedEventId, setSelectedEventId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [loginForm, setLoginForm] = useState({
    username: '90',
    password: '123456',
  })
  const [currentUser, setCurrentUser] = useState({
    nickname: '90',
    account: '90',
  })
  const [profile, setProfile] = useState(defaultProfile)

  const selectedEvent = useMemo(
    () => events.find((event) => event.id === selectedEventId) ?? events[0] ?? null,
    [events, selectedEventId],
  )

  useEffect(() => {
    if (!isLoggedIn) {
      return
    }

    let cancelled = false

    async function loadEvents() {
      setLoading(true)
      setError('')
      try {
        const eventList = await fetchEvents()
        if (cancelled) {
          return
        }
        setEvents(eventList)
        if (eventList.length > 0) {
          setSelectedEventId((current) => current || eventList[0].id)
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || '事件列表加载失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadEvents()

    return () => {
      cancelled = true
    }
  }, [isLoggedIn])

  useEffect(() => {
    if (!isLoggedIn || !selectedEventId) {
      return
    }

    if (activePage !== 'detail' && activePage !== 'qa') {
      return
    }

    let cancelled = false

    async function loadDetail() {
      setLoading(true)
      setError('')
      try {
        const detail = await fetchEventDetail(selectedEventId)
        if (cancelled) {
          return
        }
        setEvents((currentEvents) =>
          currentEvents.map((item) => (item.id === detail.id ? detail : item)),
        )
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || '事件详情加载失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadDetail()

    return () => {
      cancelled = true
    }
  }, [activePage, isLoggedIn, selectedEventId])

  async function handleLogin(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const loginResult = await loginUser(loginForm)
      const responseUser = loginResult?.user ?? {}
      setCurrentUser({
        nickname: responseUser.nickname ?? responseUser.username ?? loginForm.username ?? '用户',
        account: responseUser.username ?? loginForm.username ?? 'user',
      })
      setIsLoggedIn(true)
    } catch (loginError) {
      setError(loginError.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleProfileSubmit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await saveUserProfile(buildProfilePayload(profile))
      window.alert('配置已保存。')
    } catch (submitError) {
      setError(submitError.message || '配置保存失败')
    } finally {
      setLoading(false)
    }
  }

  function handleLogout() {
    setUserMenuOpen(false)
    setActivePage('dashboard')
    setIsLoggedIn(false)
  }

  function openEventDetail(eventId) {
    setSelectedEventId(eventId)
    setActivePage('detail')
    setUserMenuOpen(false)
  }

  if (!isLoggedIn) {
    return (
      <div className="login-screen">
        <div className="login-background">
          <div className="login-glow login-glow-a"></div>
          <div className="login-glow login-glow-b"></div>
          <div className="grid-overlay"></div>
        </div>
        <div className="login-dialog">
          <h1>登录</h1>
          <p className="login-subtitle">网络舆情事件智能分析系统</p>
          <div className="login-divider">
            <span>输入您的用户名和密码</span>
          </div>
          <form className="login-form" onSubmit={handleLogin}>
            <label>
              用户名
              <input
                value={loginForm.username}
                onChange={(changeEvent) =>
                  setLoginForm((current) => ({
                    ...current,
                    username: changeEvent.target.value,
                  }))
                }
                placeholder="请输入用户名"
              />
            </label>
            <label>
              密码
              <input
                type="password"
                value={loginForm.password}
                onChange={(changeEvent) =>
                  setLoginForm((current) => ({
                    ...current,
                    password: changeEvent.target.value,
                  }))
                }
                placeholder="请输入密码"
              />
            </label>
            <button type="submit" className="primary-button">登录</button>
            <div className="login-actions">
              <span>没有账号？</span>
              <button type="button" className="text-button">注册</button>
            </div>
            {loading ? <p className="inline-tip">正在校验登录信息...</p> : null}
            {error ? <p className="inline-tip error-text">{error}</p> : null}
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className={sidebarCollapsed ? 'app-shell collapsed' : 'app-shell'}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h2>网络舆情事件智能分析系统</h2>
        </div>

        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={item.key === activePage ? 'nav-item active' : 'nav-item'}
              onClick={() => {
                setActivePage(item.key)
                setUserMenuOpen(false)
              }}
              title={item.label}
            >
              <span className="nav-icon">{navShortLabels[item.key]}</span>
              <span className="nav-text">{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="status-card">
          <span>当前事件</span>
          <strong>{selectedEvent?.title ?? '暂无数据'}</strong>
          <small>最后更新：{selectedEvent?.updatedAt ?? '--'}</small>
          <button
            type="button"
            className="status-link"
            onClick={() => selectedEvent && setActivePage('detail')}
          >
            查看事件详情
          </button>
        </div>
      </aside>

      <div className="content-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="menu-toggle"
              onClick={() => setSidebarCollapsed((current) => !current)}
              aria-label="切换侧边栏"
            >
              <span></span>
              <span></span>
              <span></span>
            </button>
            <h1>{pageTitles[activePage]}</h1>
          </div>

          <div className="user-menu-wrap">
            <button
              type="button"
              className="user-trigger"
              onClick={() => setUserMenuOpen((current) => !current)}
            >
              <span className="avatar-circle">{currentUser.nickname.slice(0, 1).toUpperCase()}</span>
              <span className="user-name">{currentUser.nickname}</span>
            </button>
            {userMenuOpen ? (
              <div className="user-menu">
                <div className="user-menu-head">
                  <span className="avatar-circle large">{currentUser.nickname.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <strong>{currentUser.nickname}</strong>
                    <small>账号：{currentUser.account}</small>
                  </div>
                </div>
                <button type="button" className="user-menu-action" onClick={handleLogout}>
                  退出登录
                </button>
              </div>
            ) : null}
          </div>
        </header>

        <main className="main-content">
          {loading ? <div className="notice-banner">正在加载页面数据...</div> : null}
          {error ? <div className="notice-banner error-banner">{error}</div> : null}

          {activePage === 'dashboard' ? (
            <DashboardPage events={events} onOpenDetail={openEventDetail} />
          ) : null}

          {activePage === 'board' ? (
            <BoardPage
              events={events}
              selectedEventId={selectedEventId}
              onSelect={openEventDetail}
            />
          ) : null}

          {activePage === 'detail' && selectedEvent ? <DetailPage event={selectedEvent} /> : null}

          {activePage === 'qa' && selectedEvent ? (
            <QaPage
              event={selectedEvent}
              events={events}
              onSelectEvent={(eventId) => setSelectedEventId(eventId)}
            />
          ) : null}

          {activePage === 'profile' ? (
            <ProfilePage profile={profile} setProfile={setProfile} onSubmit={handleProfileSubmit} />
          ) : null}
        </main>
      </div>
    </div>
  )
}

function DashboardPage({ events, onOpenDetail }) {
  const total = events.length
  const highestHeat = total > 0 ? Math.max(...events.map((item) => item.heat)) : '--'
  const highRiskCount = events.filter((item) => item.riskLevel === '高').length

  return (
    <section className="page-grid dashboard-grid">
      <div className="summary-card">
        <span>热点事件总数</span>
        <strong>{total}</strong>
      </div>
      <div className="summary-card">
        <span>最高热度指数</span>
        <strong>{highestHeat}</strong>
      </div>
      <div className="summary-card">
        <span>高风险事件</span>
        <strong>{highRiskCount}</strong>
      </div>

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>热点事件速览</h3>
            <span>按热度展示当前重点舆情，可直接跳转到事件详情。</span>
          </div>
        </div>
        <div className="event-list">
          {events.map((item) => (
            <button key={item.id} type="button" className="event-row" onClick={() => onOpenDetail(item.id)}>
              <div>
                <strong>{item.title}</strong>
                <p>{item.summary}</p>
              </div>
              <div className="event-meta">
                <span>热度 {item.heat}</span>
                <span>风险 {item.riskLevel}</span>
                <span>{item.updatedAt}</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

function BoardPage({ events, selectedEventId, onSelect }) {
  const [sortBy, setSortBy] = useState('heat')

  const sortedEvents = useMemo(() => {
    const nextEvents = [...events]
    nextEvents.sort((left, right) => {
      if (sortBy === 'time') {
        return toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt)
      }
      return right.heat - left.heat
    })
    return nextEvents
  }, [events, sortBy])

  return (
    <section className="page-grid single-column">
      <div className="card">
        <div className="board-head">
          <div>
            <h3>舆情事件看板</h3>
            <p>
              当前排序：{sortBy === 'heat' ? '按热度从高到低' : '按时间从近到远'}
            </p>
          </div>
          <div className="sort-switch">
            <button
              type="button"
              className={sortBy === 'heat' ? 'sort-button active' : 'sort-button'}
              onClick={() => setSortBy('heat')}
            >
              按热度排序
            </button>
            <button
              type="button"
              className={sortBy === 'time' ? 'sort-button active' : 'sort-button'}
              onClick={() => setSortBy('time')}
            >
              按时间排序
            </button>
          </div>
        </div>

        <div className="board-list">
          {sortedEvents.map((item, index) => (
            <button
              key={item.id}
              type="button"
              className={item.id === selectedEventId ? 'board-card active' : 'board-card'}
              onClick={() => onSelect(item.id)}
            >
              <div className="board-rank">#{index + 1}</div>
              <div className="board-card-top">
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.summary}</p>
                </div>
                <div className="board-meta">
                  <span>热度 {item.heat}</span>
                  <span>风险 {item.riskLevel}</span>
                  <span>{item.lifecycle}</span>
                  <span>{item.updatedAt}</span>
                </div>
              </div>

              <div className="sentiment-strip">
                <div className="sentiment-strip-bar">
                  <span
                    className="positive"
                    style={{ width: `${formatRatio(item.sentiment.positive)}%` }}
                  ></span>
                  <span
                    className="neutral"
                    style={{ width: `${formatRatio(item.sentiment.neutral)}%` }}
                  ></span>
                  <span
                    className="negative"
                    style={{ width: `${formatRatio(item.sentiment.negative)}%` }}
                  ></span>
                </div>
                <div className="sentiment-strip-labels">
                  <span>正面 {formatRatio(item.sentiment.positive)}%</span>
                  <span>中性 {formatRatio(item.sentiment.neutral)}%</span>
                  <span>负面 {formatRatio(item.sentiment.negative)}%</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

function DetailPage({ event }) {
  return (
    <section className="page-grid detail-grid">
      <div className="card feature-card wide-card">
        <div className="event-story-head">
          <h3>{event.title}</h3>
        </div>
        <p className="event-story-copy">{buildEventStory(event)}</p>
        <div className="badge-row">
          <span>热度指数：{event.heat}</span>
          <span>风险等级：{event.riskLevel}</span>
          <span>生命周期：{event.lifecycle}</span>
        </div>
      </div>

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>事件概述</h3>
          </div>
        </div>
        <div className="overview-grid">
          <OverviewItem label="时间" value={event.overview?.time} />
          <OverviewItem label="地点" value={event.overview?.location} />
          <OverviewItem label="起因" value={event.overview?.cause} />
          <OverviewItem label="涉事人物" value={event.overview?.persons} />
        </div>
      </div>

      <div className="card">
        <div className="section-head simple-head">
          <div>
            <h3>关键节点时间线</h3>
            <span>事件传播过程中的主要时间节点。</span>
          </div>
        </div>
        <ul className="timeline-list">
          {event.timeline.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>发展趋势图</h3>
            <span>事件报道量随时间变化曲线，已标注关键时间节点。</span>
          </div>
        </div>
        <TrendChart
          values={event.trend}
          labels={event.trendLabels}
          highlights={event.trendHighlights}
        />
      </div>

      <div className="card">
        <div className="section-head simple-head">
          <div>
            <h3>情感分布</h3>
            <span>正面、负面、中性舆情占比。</span>
          </div>
        </div>
        <SentimentChart sentiment={event.sentiment} />
      </div>

      <div className="card">
        <div className="section-head simple-head">
          <div>
            <h3>关键词</h3>
            <span>当前事件高频关键词。</span>
          </div>
        </div>
        <div className="keyword-cloud">
          {event.keywords.map((keyword) => (
            <span key={keyword}>{keyword}</span>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="section-head simple-head">
          <div>
            <h3>平台分布</h3>
            <span>不同平台上的事件讨论占比。</span>
          </div>
        </div>
        <BarGroup
          bars={event.platforms.map((item, index) => ({
            ...item,
            color: ['#4674d8', '#15a39a', '#f0b54d', '#e36a6a'][index % 4],
          }))}
        />
      </div>

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>事件溯源与关键传播路径</h3>
            <span>展示已知报道顺序或传播链路；置信度较低时表示当前数据仍不足。</span>
          </div>
        </div>
        <div className="path-flow">
          {event.propagationPath.map((item, index) => (
            <div key={`${item.stage}-${item.time}`} className="path-step-wrap">
              <div className="path-step">
                <span className="path-stage">{item.stage}</span>
                <strong>{item.time}</strong>
                <p>{item.label}</p>
                {item.source ? <small>来源：{item.source}</small> : null}
                {item.confidence ? <small>置信度：{formatPercent(item.confidence)}</small> : null}
              </div>
              {index < event.propagationPath.length - 1 ? <span className="path-arrow">→</span> : null}
            </div>
          ))}
        </div>
      </div>

      <AuthenticityCard authenticity={event.authenticity} />

      <PropagationAnalysisCard analysis={event.propagationAnalysis} />

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>AI 分析报告</h3>
          </div>
        </div>
        <AiReportCard report={event.aiReport} />
      </div>
    </section>
  )
}

function AuthenticityCard({ authenticity }) {
  return (
    <div className="card wide-card">
      <div className="section-head simple-head">
        <div>
          <h3>真实性风险提示</h3>
          <span>根据来源、正文、发布时间和佐证信息给出初步可信度，不代表事实裁定。</span>
        </div>
      </div>
      <div className="authenticity-panel">
        <div className="authenticity-score">
          <span>{authenticity.authenticityLabel}</span>
          <strong>{formatPercent(authenticity.confidence)}</strong>
        </div>
        <div className="authenticity-copy">
          <p>{authenticity.reason}</p>
          {authenticity.warnings.length > 0 ? (
            <div className="warning-list">
              {authenticity.warnings.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function PropagationAnalysisCard({ analysis }) {
  return (
    <div className="card wide-card">
      <div className="section-head simple-head">
        <div>
          <h3>传播路径分析说明</h3>
          <span>展示 AI 对传播源头、关键节点和数据限制的解释。</span>
        </div>
      </div>
      <div className="analysis-grid">
        <div className="analysis-item">
          <span>推测源头</span>
          <strong>{analysis.origin?.description ?? '暂无明确源头'}</strong>
        </div>
        <div className="analysis-item">
          <span>溯源置信度</span>
          <strong>{formatPercent(analysis.confidence)}</strong>
        </div>
      </div>
      {analysis.keyNodes.length > 0 ? (
        <div className="key-node-list">
          {analysis.keyNodes.map((item, index) => (
            <div key={`${item.news_id ?? index}-${item.role ?? 'node'}`} className="key-node">
              <strong>{item.role ?? '关键节点'}</strong>
              <p>{item.reason ?? item.description ?? '暂无说明'}</p>
            </div>
          ))}
        </div>
      ) : null}
      {analysis.limitations.length > 0 ? (
        <div className="warning-list">
          {analysis.limitations.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function AiReportCard({ report }) {
  if (typeof report === 'string') {
    return <p>{report}</p>
  }

  return (
    <div className="report-grid">
      <ReportItem label="事件总结" value={report.summary} />
      <ReportItem label="趋势分析" value={report.trend} />
      <ReportItem label="风险解释" value={report.risk} />
      <ReportItem label="处置建议" value={report.suggestion} />
      {report.generatedAt ? <span className="report-time">生成时间：{report.generatedAt}</span> : null}
    </div>
  )
}

function ReportItem({ label, value }) {
  return (
    <div className="report-item">
      <span>{label}</span>
      <p>{value || '后端暂未返回该项内容。'}</p>
    </div>
  )
}

function QaPage({ event, events, onSelectEvent }) {
  return (
    <section className="page-grid single-column qa-page-grid">
      <div className="qa-top-grid wide-card">
        <div className="card qa-compact-card">
          <div className="section-head simple-head">
            <div>
              <h3>选择提问事件</h3>
            </div>
          </div>
          <div className="event-selector">
            {events.map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === event.id ? 'event-chip active' : 'event-chip'}
                onClick={() => onSelectEvent(item.id)}
              >
                {item.title}
              </button>
            ))}
          </div>
        </div>

        <div className="card qa-compact-card">
          <div className="section-head simple-head">
            <div>
              <h3>当前事件信息</h3>
            </div>
          </div>
          <div className="qa-context">
            <strong>{event.title}</strong>
            <p>{buildEventStory(event)}</p>
            <div className="badge-row">
              <span>时间：{event.overview?.time}</span>
              <span>地点：{event.overview?.location}</span>
              <span>热度：{event.heat}</span>
            </div>
          </div>
        </div>
      </div>

      <AiQuestionPanel event={event} />
    </section>
  )
}

function ProfilePage({ profile, setProfile, onSubmit }) {
  return (
    <section className="page-grid single-column">
      <div className="card profile-header-card">
        <div>
          <h3>个人中心</h3>
          <p>你可以自定义添加关键词和关注平台，输入后按回车或英文逗号即可生成标签。</p>
        </div>
        <div className="profile-header-stats">
          <div className="mini-stat">
            <span>关键词</span>
            <strong>{profile.keywords.length}</strong>
          </div>
          <div className="mini-stat">
            <span>平台</span>
            <strong>{profile.platforms.length}</strong>
          </div>
        </div>
      </div>

      <form className="profile-grid" onSubmit={onSubmit}>
        <div className="card">
          <div className="section-head simple-head">
            <h3>关注关键词</h3>
          </div>
          <TagEditor
            items={profile.keywords}
            suggestions={keywordSuggestions}
            placeholder="输入关键词后按回车，例如：人工智能"
            onChange={(items) => setProfile((current) => ({ ...current, keywords: items }))}
          />
        </div>

        <div className="card">
          <div className="section-head simple-head">
            <h3>关注平台</h3>
          </div>
          <TagEditor
            items={profile.platforms}
            suggestions={platformSuggestions}
            placeholder="输入平台后按回车，例如：微博"
            onChange={(items) => setProfile((current) => ({ ...current, platforms: items }))}
          />
        </div>

        <div className="card wide-card submit-strip">
          <div className="submit-strip-copy">
            <strong>当前配置</strong>
            <div className="summary-list">
              <span className="summary-pill">关键词：{profile.keywords.join('、') || '未填写'}</span>
              <span className="summary-pill">平台：{profile.platforms.join('、') || '未填写'}</span>
            </div>
          </div>
          <button type="submit" className="primary-button compact">保存配置</button>
        </div>
      </form>
    </section>
  )
}

function OverviewItem({ label, value }) {
  return (
    <div className="overview-item">
      <span>{label}</span>
      <strong>{value || '--'}</strong>
    </div>
  )
}

function TagEditor({ items, suggestions, placeholder, onChange }) {
  const [draft, setDraft] = useState('')

  function addItem(rawValue) {
    const value = rawValue.trim()
    if (!value || items.includes(value)) {
      setDraft('')
      return
    }
    onChange([...items, value])
    setDraft('')
  }

  function removeItem(item) {
    onChange(items.filter((current) => current !== item))
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      addItem(draft)
    }
    if (event.key === 'Backspace' && !draft && items.length > 0) {
      removeItem(items[items.length - 1])
    }
  }

  return (
    <div className="tag-editor">
      <div className="tag-input-box">
        {items.map((item) => (
          <span key={item} className="tag-chip">
            {item}
            <button type="button" className="tag-remove" onClick={() => removeItem(item)}>
              ×
            </button>
          </span>
        ))}
        <input
          className="tag-input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => addItem(draft)}
          placeholder={placeholder}
        />
      </div>
      <div className="suggestion-row">
        {suggestions.map((item) => (
          <button key={item} type="button" className="suggestion-button" onClick={() => addItem(item)}>
            + {item}
          </button>
        ))}
      </div>
    </div>
  )
}

function AiQuestionPanel({ event }) {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [asking, setAsking] = useState(false)

  useEffect(() => {
    setMessages([])
    setQuestion('')
  }, [event.id])

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
        event_id: event.id,
        question: content,
      })
      setMessages([...nextMessages, { role: 'assistant', content: response.answer }])
    } catch (askError) {
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: askError.message || '智能问答暂时不可用。' },
      ])
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="card wide-card qa-card">
      <div className="section-head simple-head">
        <div>
          <h3>对当前事件提问</h3>
        </div>
      </div>

      {messages.length > 0 ? (
        <div className="qa-messages">
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`qa-bubble ${message.role}`}>
              <span className="qa-role">{message.role === 'user' ? '你' : 'AI'}</span>
              <p>{message.content}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="qa-empty-state">
          你可以直接提问，例如：这个事件的主要风险点是什么？后续舆情是否还会继续升温？
        </div>
      )}

      <form className="qa-form" onSubmit={handleSubmit}>
        <textarea
          rows="3"
          value={question}
          onChange={(changeEvent) => setQuestion(changeEvent.target.value)}
          placeholder="例如：这个事件的主要风险点是什么？官方回应是否足够？"
        />
        <button type="submit" className="primary-button" disabled={asking}>
          {asking ? '正在思考...' : '发送问题'}
        </button>
      </form>
    </div>
  )
}

function TrendChart({ values, labels = [], highlights = [] }) {
  const safeValues = values.length > 0 ? values : [0, 0, 0, 0, 0, 0, 0]
  const max = Math.max(...safeValues, 1)
  const startX = 34
  const endX = 390
  const step = safeValues.length > 1 ? (endX - startX) / (safeValues.length - 1) : 0
  const highlightSet = new Set(highlights)
  const points = safeValues
    .map((value, index) => {
      const x = startX + index * step
      const y = 166 - (value / max) * 118
      return `${x},${y}`
    })
    .join(' ')

  return (
    <div className="trend-card-body">
      <svg viewBox="0 0 420 220" className="chart trend-chart">
        <path d={`M${startX} 166 H${endX}`} className="axis" />
        <path d={`M${startX} 24 V166`} className="axis" />
        <polyline points={points} className="trend-line" />
        {safeValues.map((value, index) => {
          const x = startX + index * step
          const y = 166 - (value / max) * 118
          const highlighted = highlightSet.has(index)
          return (
            <g key={`${value}-${index}`}>
              <circle cx={x} cy={y} r={highlighted ? '6' : '4'} className={highlighted ? 'trend-dot highlight' : 'trend-dot'} />
              <text x={x} y={y - 12} className="trend-value">{value}</text>
              {highlighted ? <text x={x} y={y - 28} className="trend-annotation">关键节点</text> : null}
              <text x={x} y="192" className="trend-axis-label">{labels[index] ?? `T${index + 1}`}</text>
            </g>
          )
        })}
      </svg>
      <div className="trend-highlight-row">
        {safeValues.map((value, index) =>
          highlightSet.has(index) ? (
            <span key={`${labels[index] ?? index}-${value}`} className="trend-highlight-pill">
              {labels[index] ?? `T${index + 1}`}：{value}
            </span>
          ) : null,
        )}
      </div>
    </div>
  )
}

function SentimentChart({ sentiment }) {
  const total = sentiment.positive + sentiment.neutral + sentiment.negative || 1
  const positive = Math.round((sentiment.positive / total) * 100)
  const neutral = Math.round((sentiment.neutral / total) * 100)
  const negative = Math.max(0, 100 - positive - neutral)

  return (
    <div className="sentiment-layout">
      <div className="sentiment-ring">
        <div
          className="sentiment-ring-inner"
          style={{
            background: `conic-gradient(#18a086 0% ${positive}%, #f1bb4b ${positive}% ${positive + neutral}%, #dc6b66 ${positive + neutral}% 100%)`,
          }}
        ></div>
      </div>
      <div className="legend-list">
        <span>正面 {positive}%</span>
        <span>中性 {neutral}%</span>
        <span>负面 {negative}%</span>
      </div>
    </div>
  )
}

function BarGroup({ bars }) {
  const max = Math.max(...bars.map((item) => item.value), 1)
  return (
    <div className="bar-group">
      {bars.map((item) => (
        <div key={item.label ?? item.name} className="bar-row">
          <span>{item.label ?? item.name}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(item.value / max) * 100}%`, background: item.color }}></div>
          </div>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  )
}

function buildProfilePayload(profile) {
  return {
    keywords: normalizeTagList(profile.keywords),
    platforms: normalizeTagList(profile.platforms),
  }
}

function normalizeTagList(list) {
  return Array.from(new Set((Array.isArray(list) ? list : []).map((item) => item.trim()).filter(Boolean)))
}

function formatRatio(value) {
  return Math.round((Number(value) || 0) * 100)
}

function formatPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function toTimestamp(value) {
  if (!value) {
    return 0
  }
  const normalized = String(value).replace(' ', 'T')
  const timestamp = Date.parse(normalized)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function buildEventStory(event) {
  const overview = event.overview ?? {}
  return `${overview.time ?? '近期'}，${overview.location ?? '相关区域'}发生了“${event.title}”事件，起因是${overview.cause ?? '相关原因仍在梳理'}。目前主要涉及${overview.persons ?? '相关人员'}，舆论讨论集中在${event.summary}`
}

export default App
