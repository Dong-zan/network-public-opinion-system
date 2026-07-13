import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { useRef } from 'react'
import { askEventQuestion, fetchAiReport, fetchVerifyResult, generateAiReport, verifyNews } from './api/ai.js'
import { fetchEventDetail, fetchEvents } from './api/event.js'
import { loginUser, registerUser, saveUserProfile } from './api/user.js'
import { defaultProfile, navItems } from './data/mock.js'

const pageTitles = {
  board: '舆情事件看板',
  detail: '事件详情',
  qa: '智能问答',
  profile: '个人中心',
}

const navShortLabels = {
  board: '板',
  detail: '详',
  qa: '问',
  profile: '我',
}

const keywordSuggestions = ['人工智能', '网络安全', '极端天气', '公共安全', '高校舆情']
const platformSuggestions = ['新闻网站', '微博', '论坛社区', '短视频平台', '开发者社区']

function normalizeAuthField(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function validateLoginCredentials(form) {
  const username = normalizeAuthField(form.username)
  const password = typeof form.password === 'string' ? form.password : ''

  if (!username || !password) {
    return '请输入用户名和密码。'
  }

  return ''
}

function validateRegisterCredentials(form) {
  const username = normalizeAuthField(form.username)
  const nickname = normalizeAuthField(form.nickname)
  const password = typeof form.password === 'string' ? form.password : ''

  if (!nickname) {
    return '昵称不能为空。'
  }
  if (username.length < 3) {
    return '用户名至少 3 位。'
  }
  if (password.length < 6) {
    return '密码至少 6 位。'
  }

  return ''
}

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [authMode, setAuthMode] = useState('login')
  const [activePage, setActivePage] = useState('board')
  const [events, setEvents] = useState([])
  const [selectedEventId, setSelectedEventId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [loginForm, setLoginForm] = useState({
    username: '',
    password: '',
  })
  const [registerForm, setRegisterForm] = useState({
    username: '',
    password: '',
    nickname: '',
  })
  const [currentUser, setCurrentUser] = useState({
    nickname: '用户',
    account: 'user',
  })
  const [profile, setProfile] = useState(defaultProfile)
  const [registerNotice, setRegisterNotice] = useState('')
  const mainContentRef = useRef(null)

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
        const latestReport = await fetchLatestAiReport(detail.id)
        const mergedDetail = mergeEventDisplayData(detail, latestReport)
        if (cancelled) {
          return
        }
        setEvents((currentEvents) =>
          currentEvents.map((item) =>
            item.id === mergedDetail.id
              ? mergeEventDisplayData(mergedDetail, latestReport, item)
              : item,
          ),
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

  useEffect(() => {
    if (activePage !== 'detail') {
      return
    }

    mainContentRef.current?.scrollTo({
      top: 0,
      behavior: 'auto',
    })
  }, [activePage, selectedEventId])

  async function handleLogin(event) {
    event.preventDefault()
    setError('')
    setRegisterNotice('')

    const validationMessage = validateLoginCredentials(loginForm)
    if (validationMessage) {
      setError(validationMessage)
      return
    }

    const normalizedPayload = {
      username: normalizeAuthField(loginForm.username),
      password: loginForm.password,
    }

    setLoading(true)
    try {
      const loginResult = await loginUser(normalizedPayload)
      const responseUser = loginResult?.user ?? {}
      setCurrentUser({
        nickname:
          responseUser.nickname ??
          loginResult?.nickname ??
          responseUser.username ??
          loginResult?.username ??
          loginForm.username ??
          '用户',
        account:
          responseUser.username ??
          loginResult?.username ??
          loginForm.username ??
          'user',
      })
      setIsLoggedIn(true)
    } catch (loginError) {
      setError(loginError.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleRegister(event) {
    event.preventDefault()
    setError('')
    setRegisterNotice('')

    const validationMessage = validateRegisterCredentials(registerForm)
    if (validationMessage) {
      setError(validationMessage)
      return
    }

    const normalizedPayload = {
      username: normalizeAuthField(registerForm.username),
      password: registerForm.password,
      nickname: normalizeAuthField(registerForm.nickname),
    }

    setLoading(true)

    try {
      await registerUser(normalizedPayload)
      setLoginForm({
        username: normalizedPayload.username,
        password: '',
      })
      setRegisterForm({
        username: '',
        password: '',
        nickname: '',
      })
      setAuthMode('login')
      setRegisterNotice('注册成功，请使用刚注册的账号登录。')
    } catch (registerError) {
      setError(registerError.message || '注册失败')
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
    setActivePage('board')
    setIsLoggedIn(false)
  }

  function handleRegisterClick() {
    setError('')
    setRegisterNotice('')
    setAuthMode('register')
  }

  function handleBackToLogin() {
    setError('')
    setRegisterNotice('')
    setAuthMode('login')
  }

  function openEventDetail(eventId) {
    setSelectedEventId(eventId)
    setActivePage('detail')
    setUserMenuOpen(false)
  }

  async function refreshEventDetailById(eventId, preferredReport = null) {
    if (!eventId) {
      return null
    }

    const detail = await fetchEventDetail(eventId)
    const latestReport = preferredReport ?? await fetchLatestAiReport(eventId)
    const mergedDetail = mergeEventDisplayData(detail, latestReport)
    setEvents((currentEvents) =>
      currentEvents.map((item) =>
        item.id === mergedDetail.id
          ? mergeEventDisplayData(mergedDetail, latestReport, item)
          : item,
      ),
    )
    return mergedDetail
  }

  async function handleGenerateReport(eventId) {
    const reportResult = await generateAiReport(eventId)
    const reportStatus = normalizeMaybeEmptyText(reportResult?.status) || 'success'

    if (reportStatus === 'failed') {
      setEvents((currentEvents) =>
        currentEvents.map((item) =>
          item.id === String(eventId)
            ? { ...item, aiReport: null, aiReportStatus: 'failed' }
            : item,
        ),
      )
      return { status: 'failed', report: null }
    }

    try {
      const reportResponse = await fetchAiReport(eventId)
      const latestReport = extractReportPayload(reportResponse)

      setEvents((currentEvents) =>
        currentEvents.map((item) =>
          item.id === String(eventId)
            ? mergeEventDisplayData(item, latestReport, item)
            : item,
        ),
      )

      try {
        await refreshEventDetailById(eventId, latestReport)
      } catch {
        // AI report has been updated locally; detail refresh is optional.
      }

      return {
        status: latestReport ? 'success' : 'empty',
        report: latestReport,
      }
    } catch (fetchError) {
      try {
        await refreshEventDetailById(eventId)
      } catch {
        // Ignore secondary refresh failure and surface the primary AI error.
      }

      throw fetchError
    }
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
          <h1>{authMode === 'login' ? '登录' : '注册'}</h1>
          <p className="login-subtitle">网络舆情事件智能分析系统</p>
          <div className="login-divider">
            <span>{authMode === 'login' ? '输入您的用户名和密码' : '创建一个新的系统账号'}</span>
          </div>
          <form className="login-form" onSubmit={authMode === 'login' ? handleLogin : handleRegister}>
            {authMode === 'register' ? (
              <label>
                昵称
                <input
                  value={registerForm.nickname}
                  onChange={(changeEvent) =>
                    setRegisterForm((current) => ({
                      ...current,
                      nickname: changeEvent.target.value,
                    }))
                  }
                  placeholder="请输入昵称"
                />
              </label>
            ) : null}
            <label>
              用户名
              <input
                value={authMode === 'login' ? loginForm.username : registerForm.username}
                onChange={(changeEvent) => {
                  const username = changeEvent.target.value
                  if (authMode === 'login') {
                    setLoginForm((current) => ({
                      ...current,
                      username,
                    }))
                    return
                  }
                  setRegisterForm((current) => ({
                    ...current,
                    username,
                  }))
                }}
                placeholder="请输入用户名"
              />
            </label>
            <label>
              密码
              <input
                type="password"
                value={authMode === 'login' ? loginForm.password : registerForm.password}
                onChange={(changeEvent) => {
                  const password = changeEvent.target.value
                  if (authMode === 'login') {
                    setLoginForm((current) => ({
                      ...current,
                      password,
                    }))
                    return
                  }
                  setRegisterForm((current) => ({
                    ...current,
                    password,
                  }))
                }}
                placeholder={authMode === 'login' ? '请输入密码' : '请输入至少 6 位密码'}
              />
            </label>
            <button type="submit" className="primary-button">
              {authMode === 'login' ? '登录' : '注册'}
            </button>
            <div className="login-actions">
              {authMode === 'login' ? (
                <>
                  <span>没有账号？</span>
                  <button type="button" className="text-button" onClick={handleRegisterClick}>注册</button>
                </>
              ) : (
                <>
                  <span>已有账号？</span>
                  <button type="button" className="text-button" onClick={handleBackToLogin}>返回登录</button>
                </>
              )}
            </div>
            {registerNotice ? <p className="inline-tip">{registerNotice}</p> : null}
            {loading ? <p className="inline-tip">{authMode === 'login' ? '正在校验登录信息...' : '正在提交注册信息...'}</p> : null}
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
          <small>最后更新：{formatDisplayDateTime(selectedEvent?.updatedAt) || '--'}</small>
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
            <h1>{pageTitles[activePage] ?? '舆情事件看板'}</h1>
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

        <main ref={mainContentRef} className="main-content">
          {loading ? <div className="notice-banner">正在加载页面数据...</div> : null}
          {error ? <div className="notice-banner error-banner">{error}</div> : null}

          {activePage === 'board' ? (
            <BoardHubPage
              events={events}
              selectedEventId={selectedEventId}
              onSelect={openEventDetail}
            />
          ) : null}

          {activePage === 'detail' && selectedEvent ? (
            <DetailPage event={selectedEvent} onGenerateReport={handleGenerateReport} />
          ) : null}

          {activePage === 'qa' && selectedEvent ? (
            <QaPage
              event={selectedEvent}
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

function BoardHubPage({ events, selectedEventId, onSelect }) {
  const [sortBy, setSortBy] = useState('heat')
  const total = events.length
  const highestHeat = total > 0 ? Math.max(...events.map((item) => item.heat)) : '--'
  const highRiskCount = events.filter((item) => item.riskLevel === '高').length

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
    <section className="page-grid board-hub-grid">
      <div className="board-hub-stats wide-card">
        <div className="summary-card compact">
          <span>热点事件总数</span>
          <strong>{total}</strong>
        </div>
        <div className="summary-card compact">
          <span>最高热度指数</span>
          <strong>{highestHeat}</strong>
        </div>
        <div className="summary-card compact">
          <span>高风险事件</span>
          <strong>{highRiskCount}</strong>
        </div>
      </div>

      <div className="card board-feed-card">
        <div className="section-head simple-head">
          <div>
            <h3>热点事件速览</h3>
            <span>点击查看重点事件，进入对应事件详情。</span>
          </div>
        </div>
        <div className="board-feed-list">
          {sortedEvents.map((item) => (
            <button
              key={item.id}
              type="button"
              className={item.id === selectedEventId ? 'feed-event-card active' : 'feed-event-card'}
              onClick={() => onSelect(item.id)}
            >
              <div className="feed-event-head">
                <div>
                  <strong>{item.title}</strong>
                  <p>{formatDisplayDateTime(item.updatedAt) || '--'} · {item.platforms?.[0]?.name ?? '舆情事件'}</p>
                </div>
              </div>
              <div className="feed-event-body">
                <p>{item.summary}</p>
              </div>
              <div className="feed-event-meta">
                <span>热度 {item.heat}</span>
                <span>风险 {item.riskLevel}</span>
                <span>{item.lifecycle}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="card board-rank-card">
        <div className="board-head">
          <div>
            <h3>舆情热榜</h3>
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

        <div className="board-rank-list">
          {sortedEvents.map((item, index) => (
            <button
              key={item.id}
              type="button"
              className={item.id === selectedEventId ? 'rank-row active' : 'rank-row'}
              onClick={() => onSelect(item.id)}
            >
              <div className="rank-index">{index + 1}</div>
              <div className="rank-copy">
                <strong>{item.title}</strong>
                <span className="rank-hotness">
                  {sortBy === 'heat' ? `热度 ${item.heat}` : formatDisplayDateTime(item.updatedAt) || '--'}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

function DetailPage({ event, onGenerateReport }) {
  const [reportLoading, setReportLoading] = useState(false)
  const [reportMessage, setReportMessage] = useState('')
  const [verifyLoading, setVerifyLoading] = useState(false)
  const [verifyMessage, setVerifyMessage] = useState('')
  const [selectedNewsId, setSelectedNewsId] = useState('')
  const [authenticityResult, setAuthenticityResult] = useState(null)
  const [autoVerifyKey, setAutoVerifyKey] = useState('')

  useEffect(() => {
    setReportLoading(false)
    setReportMessage('')
    setVerifyLoading(false)
    setVerifyMessage('')
    setAuthenticityResult(null)
    setSelectedNewsId('')
    setAutoVerifyKey('')
  }, [event.id])

  useEffect(() => {
    if (!selectedNewsId && event.newsList?.length > 0) {
      setSelectedNewsId(event.newsList[0].id)
    }
  }, [event.newsList, selectedNewsId])

  async function handleRefreshReport() {
    if (!onGenerateReport) {
      return
    }

    setReportLoading(true)
    setReportMessage('')

    try {
      const result = await onGenerateReport(event.id)
      const status = normalizeMaybeEmptyText(result?.status)
      if (status === 'failed') {
        setReportMessage('AI分析暂不可用')
      } else if (status === 'empty') {
        setReportMessage('AI报告已触发生成，但当前还没有可展示的报告内容。')
      } else {
        setReportMessage('AI报告已生成并刷新到当前页面。')
      }
    } catch (reportError) {
      setReportMessage(reportError.message || 'AI分析暂不可用')
    } finally {
      setReportLoading(false)
    }
  }

  async function handleVerifyAuthenticity(options = {}) {
    const { silent = false } = options

    if (!selectedNewsId) {
      if (!silent) {
        setVerifyMessage('当前事件缺少可核验的 news_id，请让后端补充新闻列表。')
      }
      return
    }

    setVerifyLoading(true)
    if (!silent) {
      setVerifyMessage('')
    }

    try {
      const verifyResponse = await verifyNews({
        event_id: event.id,
        news_id: Number(selectedNewsId) || selectedNewsId,
        max_claims: 5,
      })

      let nextResult = extractVerifyPayload(verifyResponse)

      if (!nextResult) {
        const latestVerifyResponse = await fetchVerifyResult(
          event.id,
          Number(selectedNewsId) || selectedNewsId,
        )
        nextResult = extractVerifyPayload(latestVerifyResponse)
      }

      if (nextResult) {
        setAuthenticityResult(nextResult)
        if (!silent) {
          setVerifyMessage('真实性核验结果已更新。')
        }
      } else {
        if (!silent) {
          setVerifyMessage('已发起真实性核验，但当前没有可展示的核验结果。')
        }
      }
    } catch (verifyError) {
      if (!silent) {
        setVerifyMessage(verifyError.message || '真实性核验暂不可用')
      }
    } finally {
      setVerifyLoading(false)
    }
  }

  useEffect(() => {
    if (!selectedNewsId) {
      return
    }

    const currentKey = `${event.id}:${selectedNewsId}`
    if (autoVerifyKey === currentKey) {
      return
    }

    setAutoVerifyKey(currentKey)
    handleVerifyAuthenticity({ silent: true })
  }, [autoVerifyKey, event.id, selectedNewsId])

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

      <div className="card detail-card detail-timeline-card">
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

      <div className="card detail-card detail-sentiment-card">
        <div className="section-head simple-head">
          <div>
            <h3>情感分布</h3>
            <span>正面、负面、中性舆情占比。</span>
          </div>
        </div>
        <SentimentChart sentiment={event.sentiment} />
      </div>

      <div className="card detail-card detail-keyword-card">
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

      <div className="card detail-card detail-platform-card">
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

      <AuthenticityCard
        authenticity={authenticityResult ?? event.authenticity}
        newsList={event.newsList ?? []}
        selectedNewsId={selectedNewsId}
        onSelectNews={setSelectedNewsId}
        onVerify={handleVerifyAuthenticity}
        verifyLoading={verifyLoading}
        verifyMessage={verifyMessage}
      />

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>AI 分析报告</h3>
          </div>
          <button
            type="button"
            className="action-button"
            onClick={handleRefreshReport}
            disabled={reportLoading}
          >
            {reportLoading ? '正在生成...' : '生成/刷新AI报告'}
          </button>
        </div>
        {reportMessage ? <div className="inline-panel">{reportMessage}</div> : null}
        <AiReportCard report={event.aiReport} status={event.aiReportStatus} />
      </div>
    </section>
  )
}

function AuthenticityCard({
  authenticity,
  newsList,
  selectedNewsId,
  onSelectNews,
  onVerify,
  verifyLoading,
  verifyMessage,
}) {
  const selectedNews =
    Array.isArray(newsList) && newsList.length > 0
      ? newsList.find((item) => item.id === selectedNewsId) ?? newsList[0]
      : null

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
          <span>核验结论</span>
          <strong>{buildAuthenticityHeadline(authenticity)}</strong>
          <small>{buildAuthenticitySubtitle(authenticity)}</small>
        </div>
        <div className="authenticity-copy">
          <p>{authenticity.reason}</p>
          {buildAuthenticityNotes(authenticity).length > 0 ? (
            <ul className="authenticity-note-list">
              {buildAuthenticityNotes(authenticity).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      <div className="news-verify-panel">
        <div className="verify-toolbar">
          <div className="verify-target">
            <span>当前核验样本</span>
            {newsList.length > 1 ? (
              <select
                className="news-select"
                value={selectedNewsId}
                onChange={(event) => onSelectNews(event.target.value)}
              >
                {newsList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            ) : (
              <strong>{selectedNews?.title ?? '当前事件暂无可核验样本'}</strong>
            )}
            <small>
              {selectedNews
                ? `${selectedNews.source || '来源待补充'} · ${formatDisplayDateTime(selectedNews.publishTime) || '--'}`
                : '当前事件暂无可核验新闻样本'}
            </small>
          </div>
            <button
              type="button"
              className="action-button"
              onClick={onVerify}
              disabled={verifyLoading || !selectedNewsId}
            >
            {verifyLoading ? '核验中...' : '重新核验'}
            </button>
          </div>

        {newsList.length > 0 ? (
          <>
            <div className="news-detail-card">
              <strong>当前样本说明</strong>
              <p>{selectedNews?.content || '后端暂未返回该新闻正文摘要。'}</p>
            </div>
          </>
        ) : (
          <div className="inline-panel">
            当前事件详情里还没有可选择的新闻列表或 news_id。要联通真实性核验，后端至少需要返回
            `news_list`，并包含 `news_id / title / source / publish_time`。
          </div>
        )}

        {verifyMessage ? <div className="inline-panel">{verifyMessage}</div> : null}
      </div>
    </div>
  )
}

function AiReportCard({ report, status }) {
  if (status === 'failed') {
    return <p>AI分析暂不可用</p>
  }

  if (typeof report === 'string') {
    return <p>{report}</p>
  }

  if (!report || typeof report !== 'object') {
    return <p>后端暂未返回 AI 分析报告。</p>
  }

  return (
    <div className="report-grid">
      <ReportItem label="事件总结" value={report.summary} />
      <ReportItem label="趋势分析" value={report.trendAnalysis} />
      <ReportItem label="风险分析" value={report.riskAnalysis} />
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

function QaPage({ event }) {
  return (
    <section className="page-grid single-column qa-page-grid">
      <div className="card wide-card qa-summary-card">
        <div className="section-head simple-head">
          <div>
            <h3>当前提问事件</h3>
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
      setMessages([...nextMessages, { role: 'assistant', content: buildAiAnswerText(response) }])
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
  const rawPoints = normalizeTrendChartPoints(values, labels, highlights)
  const points = rawPoints.filter(
    (item) => typeof item.value === 'number' && Number.isFinite(item.value) && item.value > 0,
  )
  const validPoints = points

  if (points.length === 0 || validPoints.length === 0) {
    return (
      <div className="trend-card-body">
        <div className="chart-empty">
          后端暂未返回有效的关键时间节点数据，当前无法绘制报道量趋势。
        </div>
      </div>
    )
  }

  const max = Math.max(...validPoints.map((item) => item.value), 1)
  const startX = 52
  const endX = 360
  const axisEndX = 384
  const axisTopY = 24
  const axisBottomY = 166
  const pointCount = points.length
  const step = pointCount > 1 ? (endX - startX) / (pointCount - 1) : 0
  const positionedPoints = points.map((item, index) => {
    const x = startX + index * step
    const y = item.value === null ? null : axisBottomY - (item.value / max) * 118
    return {
      ...item,
      x,
      y,
    }
  })
  const lineSegments = buildTrendLineSegments(positionedPoints)
  const visibleLabelIndexes = buildVisibleXAxisLabelIndexes(positionedPoints)
  const shouldRotateXAxisLabels = visibleLabelIndexes.size > 4
  const yAxisTicks = buildTrendYAxisTicks(max, axisBottomY)
  const highlightIndices = positionedPoints
    .filter((item) => item.highlighted && item.y !== null)
    .map((item) => item.index)
  const highlightOrderMap = new Map(highlightIndices.map((index, order) => [index, order]))

  return (
    <div className="trend-card-body">
      <svg viewBox="0 0 420 240" className="chart trend-chart">
        <path d={`M${startX} ${axisBottomY} H${axisEndX}`} className="axis" />
        <path d={`M${axisEndX - 10} ${axisBottomY - 6} L${axisEndX} ${axisBottomY} L${axisEndX - 10} ${axisBottomY + 6}`} className="axis-arrowhead axis-arrowhead-x" />
        <path d={`M${startX} ${axisBottomY} V${axisTopY}`} className="axis" />
        <path d={`M${startX - 6} ${axisTopY + 10} L${startX} ${axisTopY} L${startX + 6} ${axisTopY + 10}`} className="axis-arrowhead axis-arrowhead-y" />
        {yAxisTicks.map((tick) => (
          <g key={`tick-${tick.value}`}>
            <path d={`M${startX - 6} ${tick.y} H${startX}`} className="axis-tick" />
            <text x={startX - 12} y={tick.y + 4} className="axis-tick-label axis-tick-label-y">
              {tick.value}
            </text>
          </g>
        ))}
        <text x="4" y="16" className="chart-axis-title chart-axis-title-y">
          事件报道量
        </text>
        <text x={axisEndX - 6} y="210" className="chart-axis-title chart-axis-title-x">时间</text>
        {lineSegments.map((segmentPath, index) => (
          <path key={`trend-segment-${index}`} d={segmentPath} className="trend-line" />
        ))}
        {positionedPoints.map((point) => {
          const { x, y, value, index, highlighted, label, tooltipLabel } = point
          if (y === null) {
            return visibleLabelIndexes.has(index) && label ? (
              <text
                key={`axis-${index}`}
                x={x}
                y={shouldRotateXAxisLabels ? 196 : 188}
                className={shouldRotateXAxisLabels ? 'trend-axis-label trend-axis-label-rotated' : 'trend-axis-label'}
                transform={shouldRotateXAxisLabels ? `rotate(-32 ${x} 196)` : undefined}
              >
                {label}
              </text>
            ) : null
          }

          const highlightOrder = highlightOrderMap.get(index) ?? 0
          const annotationY = y - (highlightOrder % 2 === 0 ? 28 : 46)
          const annotationX = x + (highlightOrder % 2 === 0 ? 0 : 16)

          return (
            <g key={`${value}-${index}`}>
              <title>{`${tooltipLabel || label || `节点 ${index + 1}`}：${value}`}</title>
              <circle
                cx={x}
                cy={y}
                r={highlighted ? '6' : '4'}
                className={highlighted ? 'trend-dot highlight' : 'trend-dot'}
              />
              {visibleLabelIndexes.has(index) && label ? (
                <text
                  x={x}
                  y={shouldRotateXAxisLabels ? 196 : 188}
                  className={shouldRotateXAxisLabels ? 'trend-axis-label trend-axis-label-rotated' : 'trend-axis-label'}
                  transform={shouldRotateXAxisLabels ? `rotate(-32 ${x} 196)` : undefined}
                >
                  {label}
                </text>
              ) : null}
            </g>
          )
        })}
      </svg>
      <div className="trend-highlight-row">
        {positionedPoints.map((item) => (
          <span key={`${item.label || item.index}-${item.value}`} className="trend-highlight-pill">
            {(item.label || `节点 ${item.index + 1}`)}：报道量 {item.value}
          </span>
        ))}
      </div>
    </div>
  )
}

function normalizeTrendChartPoints(values, labels = [], highlights = []) {
  const valueList = Array.isArray(values) ? values : []
  const labelList = Array.isArray(labels) ? labels : []
  const pointCount = Math.max(valueList.length, labelList.length)

  if (pointCount === 0) {
    return []
  }

  const highlightSet = new Set(Array.isArray(highlights) ? highlights : [])

  return Array.from({ length: pointCount }, (_, index) => {
    const rawValue = valueList[index]
    const value =
      typeof rawValue === 'number'
        ? (Number.isFinite(rawValue) ? rawValue : null)
        : (rawValue === null || rawValue === undefined || rawValue === ''
          ? null
          : (() => {
            const normalized = Number(rawValue)
            return Number.isFinite(normalized) ? normalized : null
          })())
    const tooltipLabel = formatDisplayDateTime(labelList[index]) || normalizeMaybeEmptyText(labelList[index]) || ''
    const label = formatTrendAxisLabel(tooltipLabel)

    return {
      index,
      value,
      label,
      tooltipLabel,
      highlighted: highlightSet.has(index),
    }
  })
}

function formatTrendAxisLabel(value) {
  const text = normalizeMaybeEmptyText(value)
  if (!text) {
    return ''
  }

  if (text.length <= 10) {
    return text
  }

  return text.slice(5, 16)
}

function buildVisibleXAxisLabelIndexes(points) {
  const labeledIndices = points.filter((item) => item.label).map((item) => item.index)
  if (labeledIndices.length <= 6) {
    return new Set(labeledIndices)
  }

  const result = new Set()
  const step = Math.ceil(labeledIndices.length / 6)

  labeledIndices.forEach((index, position) => {
    if (position % step === 0 || position === labeledIndices.length - 1) {
      result.add(index)
    }
  })

  points.forEach((item) => {
    if (item.highlighted && item.label) {
      result.add(item.index)
    }
  })

  return result
}

function buildTrendLineSegments(points) {
  const segments = []
  let currentSegment = []

  points.forEach((point) => {
    if (point.y === null) {
      if (currentSegment.length > 0) {
        segments.push(buildTrendCurvePath(currentSegment))
        currentSegment = []
      }
      return
    }

    currentSegment.push(point)
  })

  if (currentSegment.length > 0) {
    segments.push(buildTrendCurvePath(currentSegment))
  }

  return segments.filter(Boolean)
}

function buildTrendCurvePath(points) {
  if (!Array.isArray(points) || points.length === 0) {
    return ''
  }

  if (points.length === 1) {
    return `M${points[0].x} ${points[0].y}`
  }

  let path = `M${points[0].x} ${points[0].y}`

  for (let index = 0; index < points.length - 1; index += 1) {
    const current = points[index]
    const next = points[index + 1]
    const controlX = (current.x + next.x) / 2

    path += ` C ${controlX} ${current.y}, ${controlX} ${next.y}, ${next.x} ${next.y}`
  }

  return path
}

function buildTrendYAxisTicks(max, axisBottomY) {
  const safeMax = Math.max(1, Math.ceil(max))
  const tickValues =
    safeMax <= 6
      ? Array.from({ length: safeMax + 1 }, (_, index) => index)
      : (() => {
          const middleValue = Math.max(1, Math.ceil(safeMax / 2))
          return Array.from(new Set([0, middleValue, safeMax])).sort((left, right) => left - right)
        })()

  return tickValues.map((value) => ({
    value,
    y: axisBottomY - (value / safeMax) * 118,
  }))
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

function formatDisplayDateTime(value) {
  const text = normalizeMaybeEmptyText(value)
  if (!text) {
    return ''
  }

  return text
    .replace('T', ' ')
    .replace(/\.\d+$/, '')
    .replace(/Z$/, '')
    .trim()
}

function toTimestamp(value) {
  const normalizedValue = formatDisplayDateTime(value)
  if (!normalizedValue) {
    return 0
  }
  const normalized = normalizedValue.replace(' ', 'T')
  const timestamp = Date.parse(normalized)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

async function fetchLatestAiReport(eventId) {
  if (!eventId) {
    return null
  }

  try {
    const response = await fetchAiReport(eventId)
    return extractReportPayload(response)
  } catch {
    return null
  }
}

function mergeEventDisplayData(detail, report, currentItem = null) {
  const currentReport =
    currentItem?.aiReport && typeof currentItem.aiReport === 'object' ? currentItem.aiReport : null
  const nextReport = report ?? currentReport
  const mergedOverview = mergeOverviewSources(detail?.overview, nextReport?.overview)

  return {
    ...detail,
    overview: mergedOverview,
    aiReport: nextReport ?? detail?.aiReport,
    aiReportStatus: nextReport ? 'success' : detail?.aiReportStatus ?? currentItem?.aiReportStatus ?? '',
  }
}

function mergeOverviewSources(eventOverview, reportOverview) {
  const base = eventOverview && typeof eventOverview === 'object' ? eventOverview : {}
  const report = reportOverview && typeof reportOverview === 'object' ? reportOverview : {}

  return {
    time: pickOverviewValue(base.time, report.time, '后端暂未返回时间信息'),
    location: pickOverviewValue(base.location, report.location, '后端暂未返回地点信息'),
    cause: pickOverviewValue(base.cause, report.cause, '后端暂未返回事件起因'),
    persons: pickOverviewValue(base.persons, report.persons, '后端暂未返回涉事人物信息'),
  }
}

function pickOverviewValue(primaryValue, fallbackValue, defaultValue) {
  if (isUsableOverviewValue(primaryValue)) {
    return primaryValue
  }

  if (isUsableOverviewValue(fallbackValue)) {
    return fallbackValue
  }

  return defaultValue
}

function isUsableOverviewValue(value) {
  const text = normalizeMaybeEmptyText(value)
  return Boolean(text) && !text.startsWith('后端暂未返回')
}

function buildEventStory(event) {
  const overview = event.overview ?? {}
  return `${overview.time ?? '近期'}，${overview.location ?? '相关区域'}发生了“${event.title}”事件，起因是${overview.cause ?? '相关原因仍在梳理'}。目前主要涉及${overview.persons ?? '相关人员'}，舆论讨论集中在${event.summary}`
}

function buildAiAnswerText(response) {
  const directText =
    typeof response === 'string' || typeof response === 'number'
      ? normalizeMaybeEmptyText(response)
      : ''
  if (directText) {
    return directText
  }

  const directAnswer = normalizeMaybeEmptyText(response?.answer)
  if (directAnswer) {
    return directAnswer
  }

  const summary = normalizeMaybeEmptyText(response?.summary)
  const trend = normalizeMaybeEmptyText(response?.trend)
  const risk = normalizeMaybeEmptyText(response?.risk)
  const suggestion = normalizeMaybeEmptyText(response?.suggestion)

  const sections = [
    summary ? `事件总结：${summary}` : '',
    trend ? `趋势分析：${trend}` : '',
    risk ? `风险解释：${risk}` : '',
    suggestion ? `处置建议：${suggestion}` : '',
  ].filter(Boolean)

  if (sections.length > 0) {
    return sections.join('\n')
  }

  return '后端已返回成功状态，但当前没有可展示的 AI 回答内容。'
}

function extractReportPayload(response) {
  if (!response || typeof response !== 'object') {
    return null
  }

  const status = normalizeMaybeEmptyText(response.status)
  if (status === 'failed') {
    return null
  }

  const rawReport =
    response.report && typeof response.report === 'object'
      ? response.report
      : response.ai_report && typeof response.ai_report === 'object'
        ? response.ai_report
        : response

  const summary = normalizeMaybeEmptyText(rawReport.summary)
  const overview = normalizeOverviewPayload(rawReport.overview)
  const trendAnalysis =
    normalizeMaybeEmptyText(rawReport.trend_analysis) ??
    normalizeMaybeEmptyText(rawReport.trendAnalysis) ??
    normalizeMaybeEmptyText(rawReport.trend)
  const riskAnalysis =
    normalizeMaybeEmptyText(rawReport.risk_analysis) ??
    normalizeMaybeEmptyText(rawReport.riskAnalysis) ??
    normalizeMaybeEmptyText(rawReport.risk)
  const suggestions = normalizeStringList(rawReport.suggestions ?? rawReport.suggestion)
  const limitations = normalizeStringList(rawReport.limitations)

  if (
    !summary &&
    Object.keys(overview).length === 0 &&
    !trendAnalysis &&
    !riskAnalysis &&
    suggestions.length === 0 &&
    limitations.length === 0
  ) {
    return null
  }

  return {
    summary: summary ?? '',
    overview,
    trendAnalysis: trendAnalysis ?? '',
    riskAnalysis: riskAnalysis ?? '',
    suggestions,
    limitations,
  }
}

function extractVerifyPayload(response) {
  if (!response || typeof response !== 'object') {
    return null
  }

  const rawResult =
    response.result && typeof response.result === 'object'
      ? response.result
      : response.data && typeof response.data === 'object'
        ? response.data
        : response

  const authenticityLabel =
    normalizeMaybeEmptyText(rawResult.authenticity_label) ??
    normalizeMaybeEmptyText(rawResult.authenticityLabel) ??
    normalizeMaybeEmptyText(rawResult.overall_verdict) ??
    normalizeMaybeEmptyText(rawResult.verdict) ??
    normalizeMaybeEmptyText(rawResult.label)
  const confidence = Number(rawResult.confidence)
  const evidenceScore = Number(rawResult.evidence_score)
  const claimResults = Array.isArray(rawResult.claim_results) ? rawResult.claim_results : []
  const reason =
    normalizeMaybeEmptyText(rawResult.reason) ??
    normalizeMaybeEmptyText(rawResult.analysis) ??
    normalizeMaybeEmptyText(rawResult.summary) ??
    normalizeMaybeEmptyText(rawResult.score_explanation) ??
    normalizeMaybeEmptyText(claimResults[0]?.explanation)
  const warnings = [
    ...normalizeStringList(rawResult.warnings ?? rawResult.risks ?? rawResult.claims),
    ...normalizeStringList(rawResult.risk_flags).map((item) => formatVerifyFlag(item)),
    ...normalizeStringList(rawResult.limitations),
    ...claimResults.flatMap((item) => normalizeStringList(item.limitations)),
  ].filter(Boolean)
  const evidence = [
    ...normalizeStringList(rawResult.evidence ?? rawResult.references),
    ...claimResults
      .map((item, index) => {
        const claim = normalizeMaybeEmptyText(item.claim) ?? `核验点 ${index + 1}`
        const explanation =
          normalizeMaybeEmptyText(item.explanation) ??
          normalizeMaybeEmptyText(item.verdict) ??
          normalizeMaybeEmptyText(item.evidence_score)

        if (!claim && !explanation) {
          return ''
        }

        return explanation ? `${claim}：${explanation}` : claim
      })
      .filter(Boolean),
  ]

  if (!authenticityLabel && !reason && warnings.length === 0 && evidence.length === 0 && !confidence) {
    return null
  }

  return {
    authenticityLabel: formatVerifyVerdictLabel(authenticityLabel ?? '信息不足'),
    confidence: Number.isFinite(confidence) ? confidence : null,
    evidenceScore: Number.isFinite(evidenceScore) ? evidenceScore : null,
    reason: reason ?? '后端已返回核验状态，但当前没有可展示的真实性分析说明。',
    warnings: Array.from(new Set(warnings)).slice(0, 3),
    evidence: Array.from(new Set(evidence)).slice(0, 2),
  }
}

function normalizeOverviewPayload(value) {
  if (!value || typeof value !== 'object') {
    return {}
  }

  const overview = {}
  const time = normalizeMaybeEmptyText(value.time)
  const location = normalizeMaybeEmptyText(value.location)
  const cause = normalizeMaybeEmptyText(value.cause)
  const persons = normalizeMaybeEmptyText(value.persons)

  if (time) {
    overview.time = time
  }
  if (location) {
    overview.location = location
  }
  if (cause) {
    overview.cause = cause
  }
  if (persons) {
    overview.persons = persons
  }

  return overview
}

function normalizeStringList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => normalizeMaybeEmptyText(item)).filter(Boolean)
  }

  const singleValue = normalizeMaybeEmptyText(value)
  return singleValue ? [singleValue] : []
}

function formatVerifyVerdictLabel(value) {
  const normalized = normalizeMaybeEmptyText(value)
  const labels = {
    supported: '基本可信',
    refuted: '存疑',
    mixed: '需进一步核验',
    insufficient_evidence: '证据不足',
    not_verifiable: '暂不可核验',
  }

  return labels[normalized] ?? normalized ?? '信息不足'
}

function formatVerifyFlag(value) {
  const normalized = normalizeMaybeEmptyText(value)
  const labels = {
    limited_independent_sources: '独立信源不足',
    conflicting_sources: '信源口径存在冲突',
    low_coverage: '有效核验覆盖度较低',
    duplicate_or_reprint_evidence_removed: '重复转载内容已去重',
  }

  return labels[normalized] ?? normalized ?? ''
}

function buildAuthenticityHeadline(authenticity) {
  return normalizeMaybeEmptyText(authenticity?.authenticityLabel) || '信息不足'
}

function buildAuthenticitySubtitle(authenticity) {
  if (authenticity?.authenticityLabel === '证据不足') {
    return '当前无法核验'
  }

  if (typeof authenticity?.confidence === 'number' && Number.isFinite(authenticity.confidence)) {
    return `可信度 ${formatPercent(authenticity.confidence)}`
  }

  if (
    typeof authenticity?.evidenceScore === 'number' &&
    Number.isFinite(authenticity.evidenceScore) &&
    authenticity.evidenceScore > 0
  ) {
    return `证据强度 ${formatPercent(authenticity.evidenceScore)}`
  }

  return '以后端核验结果为准'
}

function buildAuthenticityNotes(authenticity) {
  return [
    ...normalizeStringList(authenticity?.warnings),
    ...normalizeStringList(authenticity?.evidence),
  ]
    .filter(Boolean)
    .slice(0, 4)
}

function formatOverviewLabel(key) {
  const labels = {
    time: '时间',
    location: '地点',
    cause: '起因',
    persons: '涉事人物',
  }

  return labels[key] ?? key
}

function normalizeMaybeEmptyText(value) {
  if (value === null || value === undefined) {
    return ''
  }

  const text = String(value).trim()
  if (!text || text === 'None' || text === 'null' || text === 'undefined') {
    return ''
  }

  return text
}

export default App
