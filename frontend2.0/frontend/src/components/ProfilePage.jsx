import TagInputField from './TagInputField.jsx'

const keywordSuggestions = ['人工智能', '网络安全', '极端天气', '公共安全', '高校舆情']
const platformSuggestions = ['新闻网站', '微博', '论坛社区', '短视频平台', '开发者社区']

function ProfilePage({ profile, setProfile, onSubmit }) {
  return (
    <section className="page-grid single-column">
      <div className="card profile-hero">
        <div>
          <span className="eyebrow">偏好配置</span>
          <h3>个人中心</h3>
          <p>这里已经改成可自定义输入。你可以直接输入关键词和平台，按回车或英文逗号就会生成标签。</p>
        </div>
        <div className="profile-stats">
          <div className="profile-stat-card">
            <span>关键词</span>
            <strong>{profile.keywords.length}</strong>
          </div>
          <div className="profile-stat-card">
            <span>平台</span>
            <strong>{profile.platforms.length}</strong>
          </div>
        </div>
      </div>

      <form className="profile-stack" onSubmit={onSubmit}>
        <div className="card profile-editor-card">
          <div className="section-head compact-head">
            <h3>关注关键词</h3>
            <span>支持自定义输入</span>
          </div>
          <TagInputField
            items={profile.keywords}
            placeholder="输入关键词后按回车，例如：人工智能"
            suggestions={keywordSuggestions}
            onChange={(items) => setProfile((current) => ({ ...current, keywords: items }))}
          />
        </div>

        <div className="card profile-editor-card">
          <div className="section-head compact-head">
            <h3>关注平台</h3>
            <span>支持自定义输入</span>
          </div>
          <TagInputField
            items={profile.platforms}
            placeholder="输入平台后按回车，例如：微博"
            suggestions={platformSuggestions}
            onChange={(items) => setProfile((current) => ({ ...current, platforms: items }))}
          />
        </div>

        <div className="card profile-save-card wide-card">
          <div className="profile-save-copy">
            <h3>准备提交</h3>
            <p>右侧预览框已经删掉了。保存时仍然会按接口规范提交 `keywords` 和 `platforms` 数组。</p>
            <div className="summary-list">
              <span className="summary-pill">关键词：{profile.keywords.join('、') || '未填写'}</span>
              <span className="summary-pill">平台：{profile.platforms.join('、') || '未填写'}</span>
            </div>
          </div>
          <button type="submit" className="submit-button">保存配置</button>
        </div>
      </form>
    </section>
  )
}

export default ProfilePage
