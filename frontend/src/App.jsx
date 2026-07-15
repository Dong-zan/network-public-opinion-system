import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { useRef } from 'react'
import { askEventQuestion, fetchAiReport, fetchVerifyResult, generateAiReport, verifyNews } from './api/ai.js'
import { fetchEventDetail, fetchEvents } from './api/event.js'
import { fetchEventNews, fetchNewsList } from './api/news.js'
import { loadSavedUserProfile, loginUser, registerUser, saveUserProfile } from './api/user.js'
import { defaultProfile, navItems } from './data/mock.js'

const brandName = 'Double Think'
const brandNameZh = '大堡杏'
const systemTitle = '网络舆情事件智能分析系统'

const pageTitles = {
  board: '热点汉堡台',
  detail: '事件详情',
  newsDetail: '新闻详情',
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
  const [newsList, setNewsList] = useState([])
  const [selectedEventId, setSelectedEventId] = useState('')
  const [selectedNewsId, setSelectedNewsId] = useState('')
  const [selectedNewsSnapshot, setSelectedNewsSnapshot] = useState(null)
  const [qaTargetType, setQaTargetType] = useState('event')
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
  const [profile, setProfile] = useState(() => ({ ...defaultProfile, ...loadSavedUserProfile() }))
  const [registerNotice, setRegisterNotice] = useState('')
  const mainContentRef = useRef(null)
  const loginSceneRef = useRef(null)

  function updateMascotGaze(pointerEvent) {
    const scene = loginSceneRef.current
    if (!scene) {
      return
    }

    const bounds = scene.getBoundingClientRect()
    const gazeX = Math.max(-1, Math.min(1, ((pointerEvent.clientX - bounds.left) / bounds.width - 0.5) * 2))
    const gazeY = Math.max(-1, Math.min(1, ((pointerEvent.clientY - bounds.top) / bounds.height - 0.5) * 2))
    scene.style.setProperty('--gaze-x', gazeX.toFixed(2))
    scene.style.setProperty('--gaze-y', gazeY.toFixed(2))
  }

  function resetMascotGaze() {
    loginSceneRef.current?.style.setProperty('--gaze-x', '0')
    loginSceneRef.current?.style.setProperty('--gaze-y', '0')
  }

  const selectedEvent = useMemo(
    () => {
      if (selectedEventId) {
        return events.find((event) => event.id === selectedEventId) ?? null
      }

      if (activePage === 'newsDetail' || (activePage === 'qa' && qaTargetType === 'news')) {
        return null
      }

      return events[0] ?? null
    },
    [activePage, events, qaTargetType, selectedEventId],
  )
  const selectedNews = useMemo(
    () => newsList.find((item) => String(item.id) === String(selectedNewsId)) ?? null,
    [newsList, selectedNewsId],
  )
  const activeNews = selectedNews ?? selectedNewsSnapshot
  const sidebarCurrentItem = qaTargetType === 'news' && selectedNews ? selectedNews : selectedEvent
  const sidebarCurrentLabel = qaTargetType === 'news' ? '当前新闻' : '当前事件'
  const sidebarCurrentMeta =
    qaTargetType === 'news'
      ? `${sidebarCurrentItem?.source || '来源待补充'} · ${formatDisplayDateTime(sidebarCurrentItem?.publishTime) || '--'}`
      : `最后更新：${formatDisplayDateTime(sidebarCurrentItem?.updatedAt) || '--'}`
  const sidebarCurrentActionLabel = qaTargetType === 'news' ? '查看当前新闻' : '查看事件详情'

  useEffect(() => {
    if (!isLoggedIn) {
      return
    }

    let cancelled = false

    async function loadEvents() {
      setLoading(true)
      setError('')
      try {
        const [eventResult, newsResult] = await Promise.allSettled([
          fetchEvents(),
          fetchNewsList(),
        ])
        if (cancelled) {
          return
        }

        const eventList = eventResult.status === 'fulfilled' ? eventResult.value : []
        const fetchedNewsList = newsResult.status === 'fulfilled' ? newsResult.value : []
        setEvents(eventList)
        setNewsList(fetchedNewsList)

        if (eventList.length > 0) {
          setSelectedEventId((current) => current || eventList[0].id)
        }

        const failures = [eventResult, newsResult]
          .filter((result) => result.status === 'rejected')
          .map((result) => result.reason?.message || '请求失败')
        if (failures.length > 0) {
          setError(failures.join('；'))
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
        const [detail, eventNews] = await Promise.all([
          fetchEventDetail(selectedEventId),
          fetchEventNews(selectedEventId),
        ])
        const latestReport = await fetchLatestAiReport(detail.id)
        const mergedDetail = mergeEventDisplayData(
          {
            ...detail,
            newsList: eventNews,
          },
          latestReport,
        )
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
    if (!isLoggedIn || activePage !== 'newsDetail' || !activeNews?.id || !activeNews.eventId) {
      return
    }

    let cancelled = false

    async function loadEventNews() {
      const [eventNewsResult, eventDetailResult] = await Promise.allSettled([
        fetchEventNews(activeNews.eventId),
        fetchEventDetail(activeNews.eventId),
      ])

      if (cancelled) {
        return
      }

      const eventDetail = eventDetailResult.status === 'fulfilled' ? eventDetailResult.value : null
      const eventKeywords =
        eventDetail && Array.isArray(eventDetail.keywords)
          ? eventDetail.keywords
          : []

      if (eventDetail) {
        setEvents((currentEvents) =>
          upsertMergedEvent(currentEvents, eventDetail, eventDetail.aiReport),
        )
      }

      if (eventNewsResult.status === 'rejected') {
        setError(eventNewsResult.reason?.message || '同事件新闻加载失败')
        return
      }

      const eventNews = eventNewsResult.value

      try {
        if (eventNews.length === 0 && eventKeywords.length === 0 && !eventDetail) {
          return
        }

        setNewsList((currentNews) =>
          mergeEventNewsIntoGlobalList(
            currentNews,
            eventNews,
            eventKeywords,
            activeNews.eventId,
            eventDetail?.overview,
          ),
        )
      } catch (loadError) {
        setError(loadError.message || '新闻数据合并失败')
      }
    }

    loadEventNews()

    return () => {
      cancelled = true
    }
  }, [activeNews?.eventId, activeNews?.id, activeNews?.keywords?.length, activePage, isLoggedIn])

  useEffect(() => {
    if (activePage !== 'detail' && activePage !== 'newsDetail') {
      return
    }

    mainContentRef.current?.scrollTo({
      top: 0,
      behavior: 'auto',
    })
  }, [activePage, selectedEventId, selectedNewsId])

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
    setNewsList([])
    setSelectedNewsId('')
    setSelectedNewsSnapshot(null)
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

  function openEventDetail(eventId, newsId = '') {
    setSelectedEventId(eventId)
    setSelectedNewsId(newsId ? String(newsId) : '')
    setSelectedNewsSnapshot(null)
    setQaTargetType('event')
    setActivePage('detail')
    setUserMenuOpen(false)
  }

  function openNewsDetail(news) {
    if (!news?.id) {
      return
    }

    const resolvedEventId = resolveNewsEventId(news, events)
    setError('')
    setSelectedNewsId(String(news.id))
    setSelectedNewsSnapshot(news)
    setSelectedEventId(resolvedEventId || '')
    setQaTargetType('news')
    setActivePage('newsDetail')
    setUserMenuOpen(false)
  }

  async function refreshEventDetailById(eventId, preferredReport = null) {
    if (!eventId) {
      return null
    }

    const detail = await fetchEventDetail(eventId)
    const latestReport = preferredReport ?? await fetchLatestAiReport(eventId)
    const mergedDetail = mergeEventDisplayData(detail, latestReport)
    setEvents((currentEvents) => upsertMergedEvent(currentEvents, mergedDetail, latestReport))
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
        <div className="login-background" aria-hidden="true">
          <div className="login-checker"></div>
          <div className="login-blob login-blob-top"></div>
          <div className="login-blob login-blob-bottom"></div>
        </div>
        <section
          ref={loginSceneRef}
          className="login-scene"
          onPointerMove={updateMascotGaze}
          onPointerLeave={resetMascotGaze}
          aria-label="Double Think 品牌插画"
        >
          <div className="scene-copy">
            <p className="scene-kicker">大堡杏</p>
            <h1>欢迎进入 Double Think</h1>
            <p>把热点装进一只轻松可爱的汉堡里</p>
          </div>
          <div className="scene-spark scene-spark-a" aria-hidden="true">+</div>
          <div className="scene-spark scene-spark-b" aria-hidden="true">*</div>
          <div className="scene-apricot scene-apricot-a" aria-hidden="true"></div>
          <div className="scene-apricot scene-apricot-b" aria-hidden="true"></div>
          <div className="scene-apricot scene-apricot-c" aria-hidden="true"></div>
          <div className="scene-apricot scene-apricot-d" aria-hidden="true"></div>
          <div className="scene-apricot scene-apricot-e" aria-hidden="true"></div>
          <div className="scene-apricot scene-apricot-f" aria-hidden="true"></div>
          <div className="scene-apricot scene-apricot-g" aria-hidden="true"></div>
          <div className="scene-fries" aria-hidden="true"><i></i><i></i><i></i><i></i><b></b></div>
          <div className="scene-cola" aria-hidden="true"><i></i><b></b></div>
          <div className="scene-snack-pack" aria-hidden="true"><i></i><b></b></div>
          <div className="scene-milkshake" aria-hidden="true"><i></i><b></b></div>
          <div className="scene-nugget" aria-hidden="true"></div>
          <div className="scene-sauce" aria-hidden="true"><i></i></div>
          <div className="mascot-pair" aria-hidden="true">
            <div className="burger-mascot">
              <div className="burger-shadow"></div>
              <div className="burger-top-bun"><i></i><i></i><i></i><i></i></div>
              <div className="burger-face">
                <span className="gaze-eye gaze-eye-left"><i></i></span>
                <span className="gaze-eye gaze-eye-right"><i></i></span>
                <span className="face-cheek face-cheek-left"></span>
                <span className="face-cheek face-cheek-right"></span>
                <span className="face-mouth"></span>
              </div>
              <div className="burger-lettuce"><i></i><i></i><i></i></div>
              <div className="burger-tomato"></div>
              <div className="burger-cheese"></div>
              <div className="burger-patty"></div>
              <div className="burger-bottom-bun"></div>
            </div>
            <div className="apricot-mascot">
              <div className="apricot-leaf"></div>
              <div className="apricot-face">
                <span className="gaze-eye gaze-eye-left"><i></i></span>
                <span className="gaze-eye gaze-eye-right"><i></i></span>
                <span className="face-cheek face-cheek-left"></span>
                <span className="face-cheek face-cheek-right"></span>
                <span className="face-mouth"></span>
              </div>
            </div>
          </div>
          <p className="scene-note">今日菜单：发现、判断、理解</p>
        </section>
        <div className="login-dialog">
          <div className="login-brand-block">
            <h2>{brandName}</h2>
            <p className="login-brand-zh">{brandNameZh}</p>
          </div>
          <h1>{authMode === 'login' ? '登录' : '注册'}</h1>
          <p className="login-subtitle">{authMode === 'login' ? systemTitle : '创建一个新的系统账号'}</p>
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
          <span className="sidebar-brand-tag">{brandNameZh}</span>
          <h2>{brandName}</h2>
          <p>{systemTitle}</p>
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
          <span>{sidebarCurrentLabel}</span>
          <strong>{sidebarCurrentItem?.title ?? '暂无数据'}</strong>
          <small>{sidebarCurrentMeta}</small>
          <button
            type="button"
            className="status-link"
            onClick={() => {
              if (sidebarCurrentLabel === '当前新闻' && selectedNews) {
                setActivePage('newsDetail')
                return
              }
              if (selectedEvent) {
                setActivePage('detail')
              }
            }}
          >
            {sidebarCurrentActionLabel}
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
            <h1>{pageTitles[activePage] ?? '热点汉堡台'}</h1>
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
              newsList={newsList}
              selectedEventId={selectedEventId}
              selectedNewsId={selectedNewsId}
              profile={profile}
              onSelectNews={openNewsDetail}
              onSelectEvent={openEventDetail}
            />
          ) : null}

          {activePage === 'detail' && selectedEvent ? (
            <DetailPage
              event={selectedEvent}
              allNewsList={newsList}
              initialSelectedNewsId={selectedNewsId}
              onGenerateReport={handleGenerateReport}
              onSelectedNewsChange={(newsId) => {
                setSelectedNewsId(String(newsId || ''))
              }}
            />
          ) : null}

          {activePage === 'newsDetail' && activeNews ? (
            <NewsDetailPage
              news={activeNews}
              linkedEventId={selectedEventId}
              linkedEvent={events.find((item) => String(item.id) === String(activeNews.eventId || selectedEventId)) ?? null}
              onOpenEvent={openEventDetail}
              onGenerateReport={handleGenerateReport}
            />
          ) : null}

          {activePage === 'qa' && (selectedEvent || selectedNews) ? (
            <QaPage
              event={selectedEvent}
              news={selectedNews}
              targetType={qaTargetType}
              userName={currentUser.nickname}
            />
          ) : null}

          {activePage === 'qa' && !selectedEvent && !selectedNews ? (
            <div className="notice-banner error-banner">
              当前没有可用于智能问答的新闻或事件。
            </div>
          ) : null}

          {activePage === 'profile' ? (
            <ProfilePage profile={profile} setProfile={setProfile} onSubmit={handleProfileSubmit} />
          ) : null}
        </main>
      </div>
    </div>
  )
}

function BoardHubPage({
  events,
  newsList,
  profile,
  selectedEventId,
  selectedNewsId,
  onSelectNews,
  onSelectEvent,
}) {
  const filteredBoardData = useMemo(
    () => filterBoardContent(events, newsList, profile),
    [events, newsList, profile],
  )
  const boardEvents = useMemo(
    () => buildBoardEventList(filteredBoardData.events, filteredBoardData.newsList),
    [filteredBoardData.events, filteredBoardData.newsList],
  )
  const [sortBy, setSortBy] = useState('heat')
  const total = boardEvents.length
  const highestHeat = total > 0 ? Math.max(...boardEvents.map((item) => item.heat || 0)) : '--'
  const highRiskCount = boardEvents.filter((item) => item.riskLevel === '高').length
  const boardNewsList = useMemo(
    () => normalizeBoardNewsList(filteredBoardData.newsList),
    [filteredBoardData.newsList],
  )

  const sortedEvents = useMemo(() => {
    const nextEvents = [...boardEvents]
    nextEvents.sort((left, right) => {
      if (sortBy === 'time') {
        return toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt)
      }
      return right.heat - left.heat
    })
    return nextEvents
  }, [boardEvents, sortBy])

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
              <h3>热点新闻速览</h3>
            <span>点击查看单条新闻，进入事件详情并切换到对应新闻样本。</span>
          </div>
        </div>
        <div className="board-feed-list">
          {boardNewsList.length > 0 ? (
            boardNewsList.map((item) => {
              return (
                <button
                  key={`${item.eventId || 'unknown'}-${item.id}`}
                  type="button"
                  className={isActiveBoardNews(item, selectedEventId, selectedNewsId) ? 'feed-event-card active' : 'feed-event-card'}
                  onClick={() => onSelectNews(item)}
                >
                  <div className="feed-event-head">
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.source || '来源待补充'}</p>
                      <span className="feed-event-linkage">{formatDisplayDateTime(item.publishTime) || '--'}</span>
                    </div>
                  </div>
                <div className="feed-event-body">
                  <p>{item.content || '后端暂未返回原文预览。'}</p>
                </div>
                {getVisibleBoardNewsBadges(item).length > 0 ? (
                  <div className="badge-row">
                    {getVisibleBoardNewsBadges(item).map((badge) => (
                      <span key={badge.label}>
                        {badge.label}：{badge.value}
                      </span>
                    ))}
                  </div>
                ) : null}
              </button>
              )
            })
          ) : (
            <div className="inline-panel">
              当前接口还没有返回可用于首页展示的新闻列表。后端至少需要提供独立 `news` 数据，并带上
              `news_id / event_id / title / source / publish_time / content / summary / keywords / sentiment / heat / risk_level / stage`。
            </div>
          )}
        </div>
      </div>

      <div className="card board-rank-card">
        <div className="board-head">
          <div>
            <h3>汉堡热榜</h3>
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
              onClick={() => onSelectEvent(item.id)}
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

function NewsDetailPage({ news, linkedEventId, linkedEvent, onOpenEvent, onGenerateReport }) {
  const resolvedEventId = news?.eventId || linkedEventId || ''
  const hasEventLink = Boolean(resolvedEventId)
  const storyText = buildNewsStory(news)
  const overviewItems = getVisibleNewsOverviewItems(news?.overview)
  const newsBadges = getVisibleNewsBadges(news)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportMessage, setReportMessage] = useState('')
  const [verifyLoading, setVerifyLoading] = useState(false)
  const [verifyMessage, setVerifyMessage] = useState('')
  const [authenticityResult, setAuthenticityResult] = useState(null)

  useEffect(() => {
    setReportLoading(false)
    setReportMessage('')
    setVerifyLoading(false)
    setVerifyMessage('')
    setAuthenticityResult(null)
  }, [news?.id])

  async function handleRefreshReport() {
    if (!onGenerateReport || !resolvedEventId) {
      return
    }

    setReportLoading(true)
    setReportMessage('')

    try {
      const result = await onGenerateReport(resolvedEventId)
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

  async function handleVerifyAuthenticity() {
    if (!resolvedEventId || !news?.id) {
      setVerifyMessage('当前新闻缺少可核验的 event_id 或 news_id。')
      return
    }

    setVerifyLoading(true)
    setVerifyMessage('')

    try {
      const verifyResponse = await verifyNews({
        event_id: resolvedEventId,
        news_id: Number(news.id) || news.id,
        max_claims: 5,
      })

      let nextResult = extractVerifyPayload(verifyResponse)

      if (!nextResult && resolvedEventId) {
        const latestVerifyResponse = await fetchVerifyResult(
          resolvedEventId,
          Number(news.id) || news.id,
        )
        nextResult = extractVerifyPayload(latestVerifyResponse)
      }

      if (nextResult) {
        setAuthenticityResult(nextResult)
        setVerifyMessage('真实性核验结果已更新。')
      } else {
        setVerifyMessage('')
      }
    } catch (verifyError) {
      setVerifyMessage(verifyError.message || '真实性核验暂不可用')
    } finally {
      setVerifyLoading(false)
    }
  }

  return (
    <section className="page-grid detail-grid">
      <div className="card feature-card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>{news?.title ?? '新闻详情'}</h3>
            <span>
              {(news?.source || '来源待补充')} · {formatDisplayDateTime(news?.publishTime) || '--'}
            </span>
          </div>
          <div className="news-detail-actions">
            {hasEventLink ? (
              <button
                type="button"
                className="action-button"
                onClick={() => onOpenEvent(resolvedEventId, news.id)}
              >
                查看所属事件
              </button>
            ) : null}
            {news?.url ? (
              <a className="news-reader-link" href={news.url} target="_blank" rel="noreferrer">
                查看原链接
              </a>
            ) : null}
          </div>
        </div>
        {storyText ? <p className="event-story-copy">{storyText}</p> : null}
        {newsBadges.length > 0 ? (
          <div className="badge-row">
            {newsBadges.map((item) => (
              <span key={item.label}>
                {item.label}：{item.value}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>事件概述</h3>
          </div>
        </div>
        {overviewItems.length > 0 ? (
          <div className="overview-grid">
            {overviewItems.map((item) => (
              <OverviewItem key={item.label} label={item.label} value={item.value} />
            ))}
          </div>
        ) : (
          <p className="section-empty-text">当前新闻暂无可展示的概述信息。</p>
        )}
      </div>

      <div className="card detail-card detail-sentiment-card">
        <div className="section-head simple-head">
          <div>
            <h3>情感分布</h3>
            <span>当前新闻对应的情感分析结果。</span>
          </div>
        </div>
        <SentimentChart sentiment={news?.sentimentDistribution ?? { positive: 0, neutral: 1, negative: 0 }} />
      </div>

      <div className="card detail-card detail-keyword-card">
        <div className="section-head simple-head">
          <div>
            <h3>高频关键词</h3>
            <span>当前新闻对应的关键词提取结果。</span>
          </div>
        </div>
        <div className="keyword-cloud">
          {news?.keywords?.length > 0 ? (
            news.keywords.map((keyword) => <span key={keyword}>{keyword}</span>)
          ) : (
            <span>暂无关键词</span>
          )}
        </div>
      </div>

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>平台分布</h3>
            <span>当前新闻的来源平台信息。</span>
          </div>
        </div>
        <BarGroup
          bars={(news?.platforms ?? []).map((item, index) => ({
            ...item,
            color: ['#4674d8', '#15a39a', '#f0b54d', '#e36a6a'][index % 4],
          }))}
        />
      </div>

      <AuthenticityCard
        authenticity={authenticityResult}
        newsList={[news]}
        selectedNewsId={String(news.id)}
        onSelectNews={() => {}}
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
            disabled={reportLoading || !resolvedEventId}
          >
            {reportLoading ? '正在生成...' : '生成/刷新AI报告'}
          </button>
        </div>
        {reportMessage ? <div className="inline-panel">{reportMessage}</div> : null}
        <AiReportCard report={linkedEvent?.aiReport} status={linkedEvent?.aiReportStatus} />
      </div>
    </section>
  )
}

function DetailPage({ event, allNewsList, initialSelectedNewsId, onGenerateReport, onSelectedNewsChange }) {
  const [reportLoading, setReportLoading] = useState(false)
  const [reportMessage, setReportMessage] = useState('')
  const [verifyLoading, setVerifyLoading] = useState(false)
  const [verifyMessage, setVerifyMessage] = useState('')
  const [selectedNewsId, setSelectedNewsId] = useState(initialSelectedNewsId ? String(initialSelectedNewsId) : '')
  const [authenticityResult, setAuthenticityResult] = useState(null)
  const [autoVerifyKey, setAutoVerifyKey] = useState('')
  const mergedEventNewsList = useMemo(
    () => mergeEventNewsWithGlobal(event.newsList ?? [], allNewsList, event.id),
    [allNewsList, event.id, event.newsList],
  )

  useEffect(() => {
    const nextSelectedNewsId = resolvePreferredNewsId(mergedEventNewsList, initialSelectedNewsId)
    setReportLoading(false)
    setReportMessage('')
    setVerifyLoading(false)
    setVerifyMessage('')
    setAuthenticityResult(null)
    setSelectedNewsId(nextSelectedNewsId)
    setAutoVerifyKey('')
  }, [event.id, initialSelectedNewsId, mergedEventNewsList])

  useEffect(() => {
    if (!onSelectedNewsChange) {
      return
    }

    onSelectedNewsChange(selectedNewsId || '')
  }, [onSelectedNewsChange, selectedNewsId])

  useEffect(() => {
    if (
      (!selectedNewsId || !mergedEventNewsList.some((item) => String(item.id) === String(selectedNewsId))) &&
      mergedEventNewsList.length > 0
    ) {
      setSelectedNewsId(String(mergedEventNewsList[0].id))
    }
  }, [mergedEventNewsList, selectedNewsId])

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

    if (!event?.id || !selectedNewsId) {
      if (!silent) {
        setVerifyMessage('当前新闻缺少可核验的 event_id 或 news_id。')
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
          setVerifyMessage('')
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

  const storyText = buildEventStory(event)
  const storyBadges = getVisibleStoryBadges(event)
  const overviewItems = getVisibleOverviewItems(event.overview)
  return (
    <section className="page-grid detail-grid">
      <div className="card feature-card wide-card">
        <div className="event-story-head">
          <h3>{event.title}</h3>
        </div>
        {storyText ? <p className="event-story-copy">{storyText}</p> : null}
        {storyBadges.length > 0 ? (
          <div className="badge-row">
            {storyBadges.map((item) => (
              <span key={item.label}>
                {item.label}：{item.value}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="card wide-card">
        <div className="section-head simple-head">
          <div>
            <h3>事件概述</h3>
          </div>
        </div>
        {overviewItems.length > 0 ? (
          <div className="overview-grid">
            {overviewItems.map((item) => (
              <OverviewItem key={item.label} label={item.label} value={item.value} />
            ))}
          </div>
        ) : (
          <p className="section-empty-text">当前事件暂无可展示的概述信息。</p>
        )}
      </div>

      <EventNewsReader
        newsList={mergedEventNewsList}
        selectedNewsId={selectedNewsId}
        onSelectNews={setSelectedNewsId}
      />

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
        newsList={mergedEventNewsList}
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

function EventNewsReader({ newsList, selectedNewsId, onSelectNews }) {
  const selectedNews =
    Array.isArray(newsList) && newsList.length > 0
      ? newsList.find((item) => item.id === selectedNewsId) ?? newsList[0]
      : null
  const analysisItems = [
    { label: 'NLP 摘要', value: selectedNews?.summary },
    {
      label: '关键词',
      value: selectedNews?.keywords?.length > 0 ? selectedNews.keywords.join('、') : '',
    },
    { label: '情感倾向', value: selectedNews?.sentiment },
    {
      label: '热度',
      value: typeof selectedNews?.heat === 'number' ? String(selectedNews.heat) : '',
    },
    { label: '风险等级', value: selectedNews?.riskLevel },
    { label: '传播阶段', value: selectedNews?.lifecycle },
  ].filter((item) => isMeaningfulDisplayValue(item.value))

  return (
    <div className="card wide-card">
      <div className="section-head simple-head">
        <div>
          <h3>相关新闻原文</h3>
          <span>点击左侧新闻标题，可查看该事件下对应 news 的正文与来源信息。</span>
        </div>
      </div>

      {newsList.length > 0 ? (
        <div className="news-reader-layout">
          <div className="news-reader-list">
            {newsList.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={item.id === selectedNews?.id ? 'news-reader-item active' : 'news-reader-item'}
                onClick={() => onSelectNews(item.id)}
              >
                <span className="news-reader-index">{index + 1}</span>
                <div className="news-reader-copy">
                  <strong>{item.title}</strong>
                  <small>
                    {item.source || '来源待补充'} · {formatDisplayDateTime(item.publishTime) || '--'}
                  </small>
                </div>
              </button>
            ))}
          </div>

          <div className="news-reader-panel">
            <div className="news-reader-panel-head">
              <div>
                <strong>{selectedNews?.title ?? '当前未选择新闻'}</strong>
                <small>
                  {selectedNews
                    ? `${selectedNews.source || '来源待补充'} · ${formatDisplayDateTime(selectedNews.publishTime) || '--'}`
                    : '当前事件暂无新闻内容'}
                </small>
              </div>
              {selectedNews?.url ? (
                <a
                  className="news-reader-link"
                  href={selectedNews.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  查看原链接
                </a>
              ) : null}
            </div>

            {selectedNews?.content ? (
              <div className="news-reader-content">
                <p>{selectedNews.content}</p>
              </div>
            ) : null}

            {analysisItems.length > 0 ? (
              <div className="news-reader-analysis">
                {analysisItems.map((item) => (
                  <div className="report-item" key={item.label}>
                    <span>{item.label}</span>
                    <p>{item.value}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="inline-panel">
          当前事件详情里还没有可展示的新闻列表。要实现逐条查看 news 原文，后端至少需要返回
          `news_list`，并包含 `news_id / title / source / publish_time / content 或 summary / url`。
        </div>
      )}
    </div>
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
  const displayResult = authenticity?.conclusion ? authenticity : normalizeLegacyVerifyResult(authenticity)
  const reasons = normalizeStringList(displayResult?.reasons)
  const evidenceCards = Array.isArray(displayResult?.evidenceCards) ? displayResult.evidenceCards : []
  const uncertainties = normalizeStringList(displayResult?.uncertainties)
  const technicalDetails = Array.isArray(displayResult?.technicalDetails) ? displayResult.technicalDetails : []
  const hasDisplayResult = Boolean(displayResult)

  return (
    <div className="card wide-card">
      {hasDisplayResult ? (
        <>
          <div className="verify-result-heading">
            <h3>{displayResult.headline || '真实性风险提示'}</h3>
            {displayResult.verdict ? <strong>{displayResult.verdict}</strong> : null}
            {displayResult.conclusion ? <p>{displayResult.conclusion}</p> : null}
          </div>
          <div className="verify-result-sections">
            {reasons.length > 0 ? (
              <section className="verify-result-section">
                <h4>判断依据</h4>
                <ul className="authenticity-note-list">
                  {reasons.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {evidenceCards.length > 0 ? (
              <section className="verify-result-section">
                <h4>证据来源</h4>
                <div className="evidence-card-list">
                  {evidenceCards.map((item, index) => (
                    <article className="evidence-card" key={`${item.newsId || 'evidence'}-${index}`}>
                      <div className="evidence-card-head">
                        <strong>{item.source || '来源待补充'}</strong>
                        {item.sourceDescription ? <span>· {item.sourceDescription}</span> : null}
                      </div>
                      {item.quote ? <blockquote>{item.quote}</blockquote> : null}
                      {item.explanation ? <p>{item.explanation}</p> : null}
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
            {uncertainties.length > 0 ? (
              <section className="verify-result-section">
                <h4>核验范围</h4>
                <ul className="authenticity-note-list">
                  {uncertainties.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {technicalDetails.length > 0 ? (
              <details className="verify-technical-details">
                <summary>技术详情</summary>
                <dl>
                  {technicalDetails.map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            ) : null}
          </div>
        </>
      ) : (
        <div className="section-head simple-head">
          <div>
            <h3>真实性风险提示</h3>
          </div>
        </div>
      )}
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

function QaPage({ event, news, targetType, userName }) {
  const isNewsTarget = targetType === 'news' && news
  const storyText = isNewsTarget ? buildNewsStory(news) : buildEventStory(event)
  const summaryBadges = isNewsTarget ? getVisibleNewsQuestionBadges(news) : getVisibleSummaryBadges(event)
  const title = isNewsTarget ? news.title : event.title

  return (
    <section className="page-grid single-column qa-page-grid">
      <div className="card wide-card qa-summary-card">
        <div className="section-head simple-head">
          <div>
            <h3>{isNewsTarget ? '当前提问新闻' : '当前提问事件'}</h3>
          </div>
        </div>
        <div className="qa-context">
          <strong>{title}</strong>
          {storyText ? <p>{storyText}</p> : null}
          {summaryBadges.length > 0 ? (
            <div className="badge-row">
              {summaryBadges.map((item) => (
                <span key={item.label}>
                  {item.label}：{item.value}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <AiQuestionPanel event={event} news={isNewsTarget ? news : null} targetType={targetType} userName={userName} />
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

function AiQuestionPanel({ event, news, targetType, userName }) {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [asking, setAsking] = useState(false)
  const targetKey = targetType === 'news' && news?.id ? `news:${news.id}` : `event:${event.id}`

  useEffect(() => {
    setMessages([])
    setQuestion('')
  }, [targetKey])

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
      const payload =
        targetType === 'news' && news?.id
          ? {
              news_id: Number(news.id) || news.id,
              question: content,
            }
          : {
              event_id: event?.id,
              question: content,
            }

      const response = await askEventQuestion(payload)
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
          <h3>{targetType === 'news' && news ? '对当前新闻提问' : '对当前事件提问'}</h3>
        </div>
      </div>

      {messages.length > 0 ? (
        <div className="qa-messages">
          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`qa-bubble ${message.role}`}>
              <span className="qa-role">
                {message.role === 'user' ? (userName || '我') : 'AI'}
              </span>
              <p>{message.content}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="qa-empty-state">
          {targetType === 'news' && news
            ? '你可以直接围绕当前新闻提问，例如：这条新闻的核心风险点是什么？是否存在夸大或片面表述？'
            : '你可以直接提问，例如：这个事件的主要风险点是什么？后续舆情是否还会继续升温？'}
        </div>
      )}

      <form className="qa-form" onSubmit={handleSubmit}>
        <textarea
          rows="3"
          value={question}
          onChange={(changeEvent) => setQuestion(changeEvent.target.value)}
          placeholder={
            targetType === 'news' && news
              ? '例如：这条新闻的说法是否可信？它和整个事件的关系是什么？'
              : '例如：这个事件的主要风险点是什么？官方回应是否足够？'
          }
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
    time: pickOverviewValue(base.time, report.time),
    location: pickOverviewValue(base.location, report.location),
    cause: pickOverviewValue(base.cause, report.cause),
    persons: pickOverviewValue(base.persons, report.persons),
  }
}

function pickOverviewValue(primaryValue, fallbackValue) {
  if (isUsableOverviewValue(primaryValue)) {
    return primaryValue
  }

  if (isUsableOverviewValue(fallbackValue)) {
    return fallbackValue
  }

  return null
}

function isUsableOverviewValue(value) {
  const text = normalizeMaybeEmptyText(value)
  return Boolean(text) && !text.startsWith('后端暂未返回')
}

function buildEventStory(event) {
  const summary = normalizeMaybeEmptyText(event.summary)
  if (summary) {
    return summary
  }

  const firstNewsContent = normalizeMaybeEmptyText(event.newsList?.[0]?.content)
  if (firstNewsContent) {
    return firstNewsContent
  }

  return ''
}

function buildNewsStory(news) {
  const summary = normalizeMaybeEmptyText(news?.summary)
  if (summary) {
    return summary
  }

  return ''
}

function getVisibleOverviewItems(overview) {
  const overviewMap = [
    { label: '时间', value: overview?.time },
    { label: '地点', value: overview?.location },
    { label: '起因', value: overview?.cause },
    { label: '涉事人物', value: overview?.persons },
  ]

  return overviewMap.filter((item) => isUsableOverviewValue(item.value))
}

function getVisibleStoryBadges(event) {
  const badges = []

  if (Number(event.heat) > 0) {
    badges.push({ label: '热度指数', value: event.heat })
  }

  if (isMeaningfulDisplayValue(event.riskLevel, ['未知'])) {
    badges.push({ label: '风险等级', value: event.riskLevel })
  }

  if (isMeaningfulDisplayValue(event.lifecycle, ['未知'])) {
    badges.push({ label: '生命周期', value: event.lifecycle })
  }

  return badges
}

function getVisibleSummaryBadges(event) {
  const badges = []

  if (isUsableOverviewValue(event.overview?.time)) {
    badges.push({ label: '时间', value: event.overview.time })
  }

  if (isUsableOverviewValue(event.overview?.location)) {
    badges.push({ label: '地点', value: event.overview.location })
  }

  if (Number(event.heat) > 0) {
    badges.push({ label: '热度', value: event.heat })
  }

  return badges
}

function getVisibleNewsOverviewItems(overview) {
  const overviewMap = [
    { label: '时间', value: overview?.time },
    { label: '地点', value: overview?.location },
    { label: '起因', value: overview?.cause },
    { label: '涉事人物', value: overview?.persons },
    { label: '来源', value: overview?.source },
    { label: '所属事件', value: overview?.eventTitle },
  ]

  return overviewMap.filter((item) => isUsableOverviewValue(item.value))
}

function getVisibleNewsBadges(news) {
  const badges = []

  if (typeof news?.heat === 'number') {
    badges.push({ label: '热度指数', value: news.heat })
  }

  if (isMeaningfulDisplayValue(news?.riskLevel, ['未知'])) {
    badges.push({ label: '风险等级', value: news.riskLevel })
  }

  if (isMeaningfulDisplayValue(news?.lifecycle, ['未知'])) {
    badges.push({ label: '生命周期', value: news.lifecycle })
  }

  return badges
}

function getVisibleBoardNewsBadges(news) {
  const badges = []

  if (Number(news?.heat) > 0) {
    badges.push({ label: '热度指数', value: news.heat })
  }

  if (isMeaningfulDisplayValue(news?.riskLevel, ['未知'])) {
    badges.push({ label: '风险等级', value: news.riskLevel })
  }

  if (isMeaningfulDisplayValue(news?.lifecycle, ['未知'])) {
    badges.push({ label: '生命周期', value: news.lifecycle })
  }

  return badges
}

function getVisibleNewsQuestionBadges(news) {
  const badges = []

  if (isMeaningfulDisplayValue(news?.source)) {
    badges.push({ label: '来源', value: news.source })
  }

  if (isMeaningfulDisplayValue(formatDisplayDateTime(news?.publishTime))) {
    badges.push({ label: '时间', value: formatDisplayDateTime(news.publishTime) })
  }

  if (isMeaningfulDisplayValue(news?.eventTitle)) {
    badges.push({ label: '所属事件', value: news.eventTitle })
  }

  return badges
}

function normalizeBoardNewsList(newsList) {
  if (!Array.isArray(newsList)) {
    return []
  }

  return [...newsList].sort((left, right) => {
    const timeDiff = toTimestamp(right.publishTime) - toTimestamp(left.publishTime)
    if (timeDiff !== 0) {
      return timeDiff
    }

    return String(left.id).localeCompare(String(right.id))
  })
}

function filterBoardContent(events, newsList, profile) {
  const baseEvents = Array.isArray(events) ? events : []
  const baseNewsList = Array.isArray(newsList) ? newsList : []
  const keywordFilters = normalizeTagList(profile?.keywords).map(normalizePreferenceText)
  const platformFilters = normalizeTagList(profile?.platforms).map(normalizePreferenceText)

  if (keywordFilters.length === 0 && platformFilters.length === 0) {
    return { events: baseEvents, newsList: baseNewsList }
  }

  const isNewsVisible = (news) =>
    matchesPreferenceFilters(
      getNewsPreferenceText(news),
      getNewsPlatformText(news),
      keywordFilters,
      platformFilters,
    )

  const filteredNewsList = baseNewsList.filter(isNewsVisible)
  const filteredEvents = baseEvents.filter((event) => {
    const relatedNews = baseNewsList.filter(
      (news) => String(resolveNewsEventId(news, baseEvents)) === String(event.id),
    )
    const keywordText = [
      getEventPreferenceText(event),
      ...relatedNews.map(getNewsPreferenceText),
    ].join(' ')
    const platformText = [
      getEventPlatformText(event),
      ...relatedNews.map(getNewsPlatformText),
    ].join(' ')

    return matchesPreferenceFilters(keywordText, platformText, keywordFilters, platformFilters)
  })

  return { events: filteredEvents, newsList: filteredNewsList }
}

function matchesPreferenceFilters(keywordText, platformText, keywordFilters, platformFilters) {
  const matchesKeywords =
    keywordFilters.length === 0 || keywordFilters.some((keyword) => keywordText.includes(keyword))
  const matchesPlatforms =
    platformFilters.length === 0 || platformFilters.some((platform) => platformText.includes(platform))

  return matchesKeywords && matchesPlatforms
}

function getNewsPreferenceText(news) {
  return normalizePreferenceText([
    news?.title,
    news?.summary,
    news?.content,
    news?.eventTitle,
    ...(Array.isArray(news?.keywords) ? news.keywords : []),
  ].join(' '))
}

function getNewsPlatformText(news) {
  return normalizePreferenceText([
    news?.source,
    ...(Array.isArray(news?.platforms) ? news.platforms.map((item) => item?.name) : []),
  ].join(' '))
}

function getEventPreferenceText(event) {
  return normalizePreferenceText([
    event?.title,
    event?.summary,
    ...(Array.isArray(event?.keywords) ? event.keywords : []),
  ].join(' '))
}

function getEventPlatformText(event) {
  return normalizePreferenceText(
    (Array.isArray(event?.platforms) ? event.platforms : []).map((item) => item?.name).join(' '),
  )
}

function normalizePreferenceText(value) {
  return String(value ?? '').trim().toLocaleLowerCase()
}

function buildBoardEventList(events, newsList) {
  const baseEvents = Array.isArray(events) ? events : []
  const availableNews = Array.isArray(newsList) ? newsList : []
  const eventMap = new Map(
    baseEvents
      .filter((event) => event?.id)
      .map((event) => [
        String(event.id),
        {
          id: String(event.id),
          title: event.title || '未命名事件',
          heat: Number(event.heat) || 0,
          riskLevel: event.riskLevel || '未知',
          lifecycle: event.lifecycle || '未知',
          updatedAt: event.updatedAt || '--',
          newsCount: 0,
        },
      ]),
  )

  availableNews.forEach((news) => {
    const resolvedEventId = resolveNewsEventId(news, baseEvents)
    if (!resolvedEventId || !eventMap.has(String(resolvedEventId))) {
      return
    }

    const currentItem = eventMap.get(String(resolvedEventId))
    currentItem.newsCount += 1

    if (typeof news?.heat === 'number' && news.heat > (Number(currentItem.heat) || 0)) {
      currentItem.heat = news.heat
    }

    if (toTimestamp(news?.publishTime) > toTimestamp(currentItem.updatedAt)) {
      currentItem.updatedAt = news.publishTime
    }

    if (compareRiskLevel(news?.riskLevel, currentItem.riskLevel) > 0) {
      currentItem.riskLevel = news.riskLevel
    }

    if ((!currentItem.lifecycle || currentItem.lifecycle === '未知') && news?.lifecycle) {
      currentItem.lifecycle = news.lifecycle
    }

    if ((!currentItem.title || currentItem.title === '未命名事件') && news?.eventTitle) {
      currentItem.title = news.eventTitle
    }
  })

  eventMap.forEach((item, eventId) => {
    if (item.newsCount > 0) {
      return
    }

    const matchedEvent = baseEvents.find((event) => String(event.id) === String(eventId))
    if (Array.isArray(matchedEvent?.newsList)) {
      item.newsCount = matchedEvent.newsList.length
    }
  })

  return Array.from(eventMap.values()).filter((item) => item.id)
}

function isActiveBoardNews(news, selectedEventId, selectedNewsId) {
  if (selectedNewsId) {
    return String(news.id) === String(selectedNewsId)
  }

  return String(news.eventId) === String(selectedEventId)
}

function resolveNewsEventId(news, events) {
  if (news?.eventId) {
    return String(news.eventId)
  }

  if (!Array.isArray(events) || events.length === 0) {
    return ''
  }

  const matchedByTitle = news?.eventTitle
    ? events.find((item) => item.title === news.eventTitle)
    : null
  if (matchedByTitle?.id) {
    return String(matchedByTitle.id)
  }

  const matchedByNews = events.find((event) =>
    Array.isArray(event.newsList) &&
    event.newsList.some((item) => {
      const sameId = item.id && news?.id && String(item.id) === String(news.id)
      const sameTitle = item.title && news?.title && item.title === news.title
      const sameTime =
        item.publishTime &&
        news?.publishTime &&
        String(item.publishTime) === String(news.publishTime)

      return sameId || (sameTitle && sameTime)
    }),
  )

  return matchedByNews?.id ? String(matchedByNews.id) : ''
}

function mergeEventNewsWithGlobal(eventNewsList, globalNewsList, eventId) {
  const localNewsList = Array.isArray(eventNewsList) ? eventNewsList : []
  const availableGlobalNews = Array.isArray(globalNewsList) ? globalNewsList : []

  return localNewsList.map((item) => {
    const matchedGlobalNews = availableGlobalNews.find((news) => {
      const sameId = news.id && item.id && String(news.id) === String(item.id)
      const sameTitle = news.title && item.title && news.title === item.title
      const sameEvent = String(news.eventId || '') === String(eventId || '')

      return sameId || (sameTitle && sameEvent)
    })

    return matchedGlobalNews
      ? {
          ...item,
          ...matchedGlobalNews,
          id: item.id,
        }
      : item
  })
}

function mergeEventNewsIntoGlobalList(
  currentNewsList,
  eventNewsList,
  eventKeywords = [],
  eventId = '',
  eventOverview = {},
) {
  const currentNews = Array.isArray(currentNewsList) ? currentNewsList : []
  const eventNews = Array.isArray(eventNewsList) ? eventNewsList : []
  const fetchedById = new Map(eventNews.map((item) => [String(item.id), item]))
  const knownIds = new Set(currentNews.map((item) => String(item.id)))

  const mergedCurrentNews = currentNews.map((existing) => {
    const fetched = fetchedById.get(String(existing.id))
    if (!fetched) {
      return String(existing.eventId) === String(eventId) && !existing.keywords?.length && eventKeywords.length
        ? { ...existing, keywords: eventKeywords }
        : existing
    }

    return {
      ...existing,
      ...fetched,
      title: fetched.title || existing.title,
      source: fetched.source || existing.source,
      publishTime: fetched.publishTime || existing.publishTime,
      content: fetched.content || existing.content,
      summary: fetched.summary || existing.summary,
      overview: mergeNewsOverview(eventOverview, existing.overview, fetched.overview),
      keywords: fetched.keywords?.length
        ? fetched.keywords
        : existing.keywords?.length
          ? existing.keywords
          : eventKeywords,
      heat: fetched.heat ?? existing.heat,
      riskLevel: fetched.riskLevel || existing.riskLevel,
      lifecycle: fetched.lifecycle || existing.lifecycle,
      sentiment: fetched.sentiment || existing.sentiment,
      eventId: fetched.eventId || existing.eventId,
      eventTitle: fetched.eventTitle || existing.eventTitle,
    }
  })

  return [
    ...mergedCurrentNews,
    ...eventNews
      .filter((item) => !knownIds.has(String(item.id)))
      .map((item) => ({
        ...item,
        keywords: item.keywords?.length ? item.keywords : eventKeywords,
        overview: mergeNewsOverview(eventOverview, item.overview),
      })),
  ]
}

function mergeNewsOverview(...overviews) {
  return overviews.reduce((mergedOverview, overview) => {
    if (!overview || typeof overview !== 'object') {
      return mergedOverview
    }

    Object.entries(overview).forEach(([key, value]) => {
      if (isUsableOverviewValue(value)) {
        mergedOverview[key] = value
      }
    })
    return mergedOverview
  }, {})
}

function compareRiskLevel(leftRiskLevel, rightRiskLevel) {
  const riskPriority = {
    高: 3,
    中: 2,
    低: 1,
    未知: 0,
  }

  const left = riskPriority[leftRiskLevel] ?? 0
  const right = riskPriority[rightRiskLevel] ?? 0
  return left - right
}

function resolvePreferredNewsId(newsList, preferredNewsId) {
  if (!preferredNewsId || !Array.isArray(newsList)) {
    return ''
  }

  const matchedNews = newsList.find((item) => String(item.id) === String(preferredNewsId))
  return matchedNews ? matchedNews.id : ''
}

function upsertMergedEvent(currentEvents, detail, latestReport) {
  const nextEvents = Array.isArray(currentEvents) ? [...currentEvents] : []
  const matchedIndex = nextEvents.findIndex((item) => item.id === detail.id)

  if (matchedIndex >= 0) {
    nextEvents[matchedIndex] = mergeEventDisplayData(detail, latestReport, nextEvents[matchedIndex])
    return nextEvents
  }

  nextEvents.unshift(mergeEventDisplayData(detail, latestReport))
  return nextEvents
}

function isMeaningfulDisplayValue(value, invalidValues = []) {
  const text = normalizeMaybeEmptyText(value)
  return Boolean(text) && !invalidValues.includes(text)
}

function buildAiAnswerText(response) {
  const directText =
    typeof response === 'string' || typeof response === 'number'
      ? normalizeMaybeEmptyText(response)
      : ''
  if (directText) {
    return stripAiMarkdown(directText)
  }

  const directAnswer = normalizeMaybeEmptyText(response?.answer)
  if (directAnswer) {
    return stripAiMarkdown(directAnswer)
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
    return stripAiMarkdown(sections.join('\n'))
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

  const envelope =
    response.data && typeof response.data === 'object'
      ? response.data
      : response.result && typeof response.result === 'object'
        ? response.result
        : response
  const displayResult =
    envelope.display_result && typeof envelope.display_result === 'object'
      ? envelope.display_result
      : response.display_result && typeof response.display_result === 'object'
        ? response.display_result
        : null

  if (displayResult) {
    return normalizeDisplayVerifyResult(displayResult, envelope)
  }

  return normalizeLegacyVerifyResult(envelope)
}

function normalizeDisplayVerifyResult(displayResult, envelope) {
  const headline = normalizeMaybeEmptyText(displayResult.headline)
  const conclusion = normalizeMaybeEmptyText(displayResult.conclusion)
  const reasons = normalizeStringList(displayResult.reasons)
  const uncertainties = normalizeStringList(displayResult.uncertainties)
  const evidenceCards = Array.isArray(displayResult.evidence_cards)
    ? displayResult.evidence_cards.map(normalizeEvidenceCard).filter(Boolean)
    : []
  const verdict = resolveVerifyVerdict(
    displayResult.verdict ?? displayResult.status ?? displayResult.result,
    evidenceCards,
  )

  if (!headline && !conclusion && reasons.length === 0 && evidenceCards.length === 0 && uncertainties.length === 0) {
    return null
  }

  return {
    headline,
    verdict,
    conclusion: conclusion ?? '后端暂未返回可展示的核验结论。',
    reasons,
    evidenceCards,
    uncertainties,
    technicalDetails: collectVerifyTechnicalDetails(displayResult, envelope),
  }
}

function normalizeLegacyVerifyResult(rawResult) {
  if (!rawResult || typeof rawResult !== 'object') {
    return null
  }

  const legacyConclusion =
    normalizeMaybeEmptyText(rawResult.authenticity_label) ??
    normalizeMaybeEmptyText(rawResult.authenticityLabel) ??
    normalizeMaybeEmptyText(rawResult.overall_verdict) ??
    normalizeMaybeEmptyText(rawResult.verdict) ??
    normalizeMaybeEmptyText(rawResult.label)
  const reason =
    normalizeMaybeEmptyText(rawResult.reason) ??
    normalizeMaybeEmptyText(rawResult.analysis) ??
    normalizeMaybeEmptyText(rawResult.summary)
  const uncertainties = normalizeStringList(rawResult.warnings ?? rawResult.limitations)
  const evidenceCards = normalizeStringList(rawResult.evidence ?? rawResult.references).map((quote, index) => ({
    newsId: String(index + 1),
    source: '来源待补充',
    sourceDescription: '',
    quote,
    stance: '',
    stanceKey: '',
    explanation: '',
    url: '',
  }))

  if (!legacyConclusion && !reason && uncertainties.length === 0 && evidenceCards.length === 0) {
    return null
  }

  return {
    headline: null,
    verdict: formatVerifyVerdictLabel(legacyConclusion),
    conclusion: reason ?? '后端暂未返回可展示的核验结论。',
    reasons: [],
    evidenceCards,
    uncertainties,
    technicalDetails: collectVerifyTechnicalDetails(rawResult),
  }
}

function normalizeEvidenceCard(card) {
  if (!card || typeof card !== 'object') {
    return null
  }

  const source = normalizeMaybeEmptyText(card.source)
  const quote = normalizeMaybeEmptyText(card.quote)
  const explanation = normalizeMaybeEmptyText(card.explanation)
  const sourceDescription = normalizeMaybeEmptyText(card.source_description)
  const stanceKey = normalizeMaybeEmptyText(card.stance)

  if (!source && !quote && !explanation) {
    return null
  }

  return {
    newsId: normalizeMaybeEmptyText(card.news_id),
    source: source ?? '来源待补充',
    sourceDescription: sourceDescription ?? '',
    quote: quote ?? '',
    stance: formatVerifyStance(stanceKey),
    stanceKey: stanceKey ?? '',
    explanation: explanation ?? '',
    url: normalizeVerifyUrl(card.url),
  }
}

function collectVerifyTechnicalDetails(displayResult, envelope = {}) {
  const labels = {
    evidence_score: '证据评分',
    risk_score: '风险评分',
    assessment_confidence: '评估置信度',
    relevance_score: '相关性评分',
    reason_code: '原因代码',
    score_breakdown: '评分明细',
  }

  return Object.entries(labels)
    .map(([key, label]) => {
      const value = displayResult[key] ?? envelope[key]
      const formattedValue = formatVerifyTechnicalValue(value)
      return formattedValue ? { label, value: formattedValue } : null
    })
    .filter(Boolean)
}

function formatVerifyTechnicalValue(value) {
  if (value === null || value === undefined || value === '') {
    return ''
  }

  if (Array.isArray(value)) {
    return value.map(formatVerifyTechnicalValue).filter(Boolean).join('；')
  }

  if (typeof value === 'object') {
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${formatVerifyTechnicalValue(item)}`)
      .filter(Boolean)
      .join('；')
  }

  return String(value)
}

function normalizeVerifyUrl(value) {
  const url = normalizeMaybeEmptyText(value)
  return url && /^https?:\/\//i.test(url) ? url : ''
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
    supported: '多来源支持',
    contradicted: '多来源反驳',
    conflicting: '信息存在冲突',
    insufficient_evidence: '证据不足',
    not_verifiable: '暂不可核验',
  }

  return labels[normalized] ?? normalized ?? '证据不足'
}

function resolveVerifyVerdict(value, evidenceCards) {
  const normalized = normalizeMaybeEmptyText(value)
  if (normalized) {
    return formatVerifyVerdictLabel(normalized)
  }

  const stances = evidenceCards.map((item) => item.stanceKey).filter(Boolean)
  const supportCount = stances.filter((item) => item === 'supports').length
  const contradictCount = stances.filter((item) => item === 'contradicts').length

  if (supportCount > 0 && contradictCount > 0) {
    return '信息存在冲突'
  }
  if (supportCount >= 2) {
    return '多来源支持'
  }
  if (contradictCount >= 2) {
    return '多来源反驳'
  }

  return '证据不足'
}

function formatVerifyStance(value) {
  const normalized = normalizeMaybeEmptyText(value)
  const labels = {
    supports: '支持',
    contradicts: '反驳',
    updates: '更新',
    context: '背景信息',
  }

  return labels[normalized] ?? normalized ?? ''
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

function stripAiMarkdown(text) {
  const content = normalizeMaybeEmptyText(text)
  if (!content) {
    return ''
  }

  return content.replace(/\*\*/g, '').trim()
}

export default App
