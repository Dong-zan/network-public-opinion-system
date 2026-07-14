"""
Crawler 模块 —— 网络舆情事件智能分析系统
=======================================
负责多源数据采集（新闻网站+社交平台）、数据清洗、去重、输出统一 JSON 格式。

公开 API：
    from crawler import run_once
    articles = run_once()                   # 真实采集
    articles = run_once(max_articles=50)    # 限制篇数

输出格式（每条 15 个字段）：
    {
        "title":         str,   # 新闻标题/首行文字
        "content":       str,   # 正文纯文本
        "source":        str,   # 来源（人民网/新华网/中新网/新浪新闻/微博）
        "url":           str,   # 原文链接
        "publish_time":  str,   # 发布时间 YYYY-MM-DD HH:MM:SS
        "platform":      str,   # 新闻网站 / 微博
        "author":        str,   # 作者或发布账号
        "account_id":    str,   # 平台账号ID
        "account_name":  str,   # 平台账号名称
        "account_type":  str,   # 媒体/官方机构/大V/普通用户
        "is_official":   bool,  # 是否官媒或权威来源
        "crawl_time":    str,   # 采集时间
        "repost_count":  int,   # 转发量
        "comment_count": int,   # 评论量
        "like_count":    int,   # 点赞量
        "reference_urls":list,  # 正文引用链接
    }

输出文件：
    output/YYYY-MM-DD.json     # JSON 数组，同一天多次运行自动合并去重

后端集成：
    from crawler import run_once
    articles = run_once()  # → list[dict]
"""

from crawler.pipeline import run_once

__all__ = ["run_once"]
