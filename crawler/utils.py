"""
工具函数
=======
日志配置、日期解析、HTTP 请求头。
"""

import re
import sys
import logging
from datetime import datetime
from typing import Optional

from crawler.config import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT


# ============================================================
# 日志
# ============================================================

def setup_logger(name: str = "crawler") -> logging.Logger:
    """创建控制台日志记录器（UTF-8 编码，Windows 兼容）"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        # Windows 下强制 UTF-8，避免中文乱码
        if hasattr(handler.stream, "reconfigure"):
            handler.stream.reconfigure(encoding="utf-8")
        handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(handler)

    return logger


# ============================================================
# 简单 User-Agent
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


# ===========================================================
# 日期解析
# ============================================================

# 常见中文日期格式 → strptime 模式
_DATE_PATTERNS = [
    (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "%Y-%m-%d %H:%M:%S"),
    (r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}",       "%Y-%m-%d %H:%M"),
    (r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", "%Y/%m/%d %H:%M:%S"),
    (r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}",       "%Y/%m/%d %H:%M"),
    (r"\d{4}年\d{2}月\d{2}日 \d{2}:\d{2}:\d{2}", "%Y年%m月%d日 %H:%M:%S"),
    (r"\d{4}年\d{2}月\d{2}日 \d{2}:\d{2}",       "%Y年%m月%d日 %H:%M"),
    (r"\d{4}年\d{2}月\d{2}日\d{2}:\d{2}",         "%Y年%m月%d日%H:%M"),
    (r"\d{4}年\d{2}月\d{2}日",                    "%Y年%m月%d日"),
    (r"\d{2}月\d{2}日 \d{2}:\d{2}",               "%m月%d日 %H:%M"),
]


def parse_datetime(text: str) -> str:
    """
    尝试从文本中提取并解析日期时间。

    支持格式示例：
        - 2026-07-08 14:30:00
        - 2026/07/08 14:30
        - 2026年07月08日 14:30
        - 7月8日 14:30

    Returns:
        ISO 格式字符串 "YYYY-MM-DD HH:MM:SS"，解析失败返回空字符串。
    """
    text = text.strip()
    for pattern, fmt in _DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                dt = datetime.strptime(match.group(), fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
    return ""


def normalize_publish_time(value) -> Optional[str]:
    """将发布时间规范为MySQL DATETIME可接受的字符串，非法值返回None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    text = str(value).strip()
    if not text:
        return None
    try:
        parsed_datetime = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed_datetime.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        parsed = parse_datetime(text)
        return parsed or None


# ============================================================
# 正文噪声清理
# ============================================================

# 常见的无关页脚文本模式
_NOISE_PATTERNS = [
    # 责任编辑/来源
    r"责任编辑[：:].*",
    r"责编[：:].*",
    r"（责任编辑.*?）",
    r"本文来源[：:].*",
    r"【责任编辑.*?】",
    r"原标题[：:].*",
    # 页面功能按钮
    r"分享到[：:].*",
    r"推荐阅读[：:]?.*",
    r"相关新闻[：:]?.*",
    r"返回.*顶部",
    r"分享让更多人看到",
    # 图片序号（人民网图集）
    r"^【\d+】\s*$",
    r"^\s*【\d+】\s*$",
    # 单独的括号（分享按钮残留）
    r"^\s*\(\s*$",
    r"^\s*\)\s*$",
    # 人民网版权尾部（后面内容全部截断，用特殊标记处理）
    r"人 民 网 股 份 有 限 公 司.*",
    r"Copyright ©.*",
]


def remove_noise_lines(text: str) -> str:
    """删除常见的无关页脚行（使用多行模式匹配行首行尾）"""
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)
    # 清理产生的连续空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
