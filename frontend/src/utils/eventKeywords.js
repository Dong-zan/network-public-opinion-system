export const DEFAULT_KEYWORD_LIMIT = 15

export const KEYWORD_CATEGORIES = [
  { key: 'entities', label: '核心实体' },
  { key: 'actions', label: '事件行为' },
  { key: 'attention', label: '舆情关注' },
]

const GENERIC_NEWS_WORDS = new Set([
  '比赛',
  '球员',
  '球队',
  '视频',
  '新闻',
  '北京时间',
  '记者',
  '报道',
  '媒体',
  '消息',
  '现场',
  '最新',
  '相关',
  '事件',
  '网友',
  '表示',
  '认为',
  '进行',
])

const EXACT_TIME_WORDS = new Set([
  '时间',
  '日期',
  '今天',
  '今日',
  '昨天',
  '昨日',
  '明天',
  '本周',
  '上周',
  '下周',
  '本月',
  '上月',
  '下月',
  '今年',
  '去年',
  '明年',
  '上午',
  '中午',
  '下午',
  '晚上',
  '凌晨',
])

const ATTENTION_MARKERS = [
  '争议', '质疑', '热议', '讨论', '舆论', '舆情', '关注', '焦点', '话题', '热搜',
  '愤怒', '担忧', '焦虑', '不满', '支持', '反对', '同情', '情绪', '对立', '冲突',
  '谣言', '造假', '虚假', '真相', '公信力', '黑幕', '黑哨', '网暴', '网络暴力',
]

const ACTION_MARKERS = [
  '回应', '通报', '调查', '核查', '复核', '澄清', '辟谣', '道歉', '声明', '公布',
  '发布', '宣布', '处罚', '处分', '停职', '撤职', '起诉', '判决', '立案', '逮捕',
  '救援', '处置', '整改', '改进', '维持', '取消', '暂停', '恢复', '下架', '封禁',
  '上涨', '下跌', '增长', '下降', '升级', '恶化', '扩散', '发酵', '爆发', '发生',
  '事故', '泄漏', '坍塌', '火灾', '爆炸', '伤亡', '失联', '获胜', '夺冠', '晋级',
]

const ENTITY_SUFFIXES = [
  '公司', '集团', '企业', '银行', '大学', '学院', '学校', '医院', '协会', '基金会',
  '委员会', '政府', '警方', '法院', '检察院', '公安局', '管理局', '部门', '机构', '组织',
  '足联', '联盟', '总会', '研究院', '研究所', '中心', '电视台', '报社',
  '代表队', '国家队', '俱乐部', '联赛', '杯', '锦标赛', '运动会', '奥运会', '峰会', '论坛',
]

const COUNTRY_NAMES = new Set([
  '中国', '美国', '英国', '法国', '德国', '俄罗斯', '乌克兰', '日本', '韩国', '朝鲜',
  '印度', '加拿大', '澳大利亚', '巴西', '阿根廷', '意大利', '西班牙', '葡萄牙',
  '以色列', '伊朗', '伊拉克', '沙特', '新加坡', '马来西亚', '印度尼西亚', '泰国',
  '越南', '菲律宾', '南非', '墨西哥', '土耳其', '欧盟',
])

const COMMON_CHINESE_SURNAMES = /^[赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗宣丁贲邓郁单杭洪包诸左石崔吉龚程嵇邢滑裴陆荣翁荀羊於惠甄曲封芮储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘厉戎祖武符刘景詹束龙叶幸司韶黎乔苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧阳司马上官诸葛东方皇甫尉迟公孙慕容司徒司空]/

function normalizeKeyword(value) {
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value).trim()
  }
  return ''
}

function isTimeWord(keyword) {
  if (EXACT_TIME_WORDS.has(keyword)) {
    return true
  }

  return /^\d{2,4}年$/.test(keyword)
    || /^(?:\d{2,4}年)?\d{1,2}月(?:\d{1,2}[日号])?$/.test(keyword)
    || /^\d{1,2}[日号]$/.test(keyword)
    || /^\d{1,2}(?:时|点|分钟|秒)$/.test(keyword)
    || /^\d{1,2}[:：]\d{2}$/.test(keyword)
    || /^星期[一二三四五六日天]$/.test(keyword)
    || /^周[一二三四五六日天]$/.test(keyword)
}

export function isMeaningfulEventKeyword(value) {
  const keyword = normalizeKeyword(value)

  if (!keyword || Array.from(keyword).length <= 1) {
    return false
  }
  if (/^[\d０-９.,，。%％+＋-－/\\:：]+$/.test(keyword)) {
    return false
  }
  if (isTimeWord(keyword) || GENERIC_NEWS_WORDS.has(keyword)) {
    return false
  }

  return true
}

export function classifyEventKeyword(keyword) {
  if (ATTENTION_MARKERS.some((marker) => keyword.includes(marker))) {
    return 'attention'
  }
  if (ACTION_MARKERS.some((marker) => keyword.includes(marker))) {
    return 'actions'
  }
  if (
    COUNTRY_NAMES.has(keyword)
    || ENTITY_SUFFIXES.some((suffix) => keyword.endsWith(suffix))
    || keyword.includes('·')
    || (/^[\u4e00-\u9fff]{2,4}$/.test(keyword) && COMMON_CHINESE_SURNAMES.test(keyword))
  ) {
    return 'entities'
  }

  // 缺少后端实体类型时，保留有效主题词并作为高频讨论点展示。
  return 'attention'
}

export function prepareEventKeywords(keywords, limit = Number.POSITIVE_INFINITY) {
  const seen = new Set()
  const validKeywords = []

  for (const value of Array.isArray(keywords) ? keywords : []) {
    const keyword = normalizeKeyword(value)
    const dedupeKey = keyword.toLocaleLowerCase('zh-CN')
    if (!isMeaningfulEventKeyword(keyword) || seen.has(dedupeKey)) {
      continue
    }
    seen.add(dedupeKey)
    validKeywords.push(keyword)
  }

  const visibleKeywords = validKeywords.slice(0, Math.max(0, limit))
  const groups = KEYWORD_CATEGORIES.map((category) => ({
    ...category,
    keywords: visibleKeywords.filter((keyword) => classifyEventKeyword(keyword) === category.key),
  })).filter((category) => category.keywords.length > 0)

  return {
    groups,
    total: validKeywords.length,
    hasMore: validKeywords.length > visibleKeywords.length,
  }
}
