"""
Crawler 模块 —— 网络舆情事件智能分析系统
=======================================
负责新闻采集、数据清洗、去重、输出统一 JSON 格式。

公开 API：
    from crawler import run_once
    articles = run_once()                   # 真实采集
    articles = run_once(max_articles=50)    # 限制篇数

输出格式（每条 5 个字段）：
    {
        "title":        str,   # 新闻标题
        "content":      str,   # 正文纯文本
        "source":       str,   # 新闻源（人民网 / 新华网 / 中新网）
        "url":          str,   # 原文链接
        "publish_time": str,   # 发布时间 YYYY-MM-DD HH:MM:SS
    }

输出文件：
    output/YYYY-MM-DD.json     # JSON 数组，同一天多次运行自动合并去重

后端集成：
    from crawler import run_once
    articles = run_once()  # → list[dict]
"""

from crawler.pipeline import run_once

__all__ = ["run_once"]
