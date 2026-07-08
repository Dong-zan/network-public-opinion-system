"""
Crawler 模块入口
===============
支持以下运行模式：

    python -m crawler.run               # 单次采集
    python -m crawler.run --max 50      # 单次，最多 50 篇
    python -m crawler.run --loop 10     # 持续采集，每 10 分钟一轮
"""

import argparse
import sys
import time
from datetime import datetime

from crawler.pipeline import run_once


def main():
    parser = argparse.ArgumentParser(
        description="网络舆情系统 - 新闻采集模块",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m crawler.run              单次采集
  python -m crawler.run --max 50     单次最多50篇
  python -m crawler.run --loop 10    每10分钟自动采集一轮
        """,
    )
    parser.add_argument(
        "--max", type=int, default=None,
        help="最多采集篇数（默认取自 config.MAX_ARTICLES_PER_RUN）"
    )
    parser.add_argument(
        "--loop", type=float, default=None, metavar="MINUTES",
        help="持续采集模式，每隔指定分钟运行一轮"
    )
    args = parser.parse_args()

    try:
        if args.loop:
            _run_loop(args)
        else:
            _run_once(args)
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n运行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _run_once(args):
    """单次采集"""
    print("运行模式: 完整采集\n")

    articles = run_once(max_articles=args.max)

    count = len(articles)
    if count > 0:
        print(f"\n本轮新增 {count} 篇:")
        for i, a in enumerate(articles, 1):
            print(f"  {i:2d}. {a['title'][:50]}")
            print(f"      {a['publish_time']} | {a['source']}")
    else:
        print("\n本轮无新增文章（全部重复或为空）")


def _run_loop(args):
    """持续采集：每隔 N 分钟运行一轮"""
    interval = args.loop
    total = 0
    round_num = 0

    print(f"持续采集模式：每 {interval} 分钟一轮，Ctrl+C 停止")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    while True:
        round_num += 1
        start = time.time()

        print(f"══════════ 第 {round_num} 轮 {datetime.now().strftime('%H:%M:%S')} ══════════")

        articles = run_once(max_articles=args.max)

        count = len(articles)
        total += count

        if count > 0:
            print(f"本轮新增 {count} 篇（累计 {total} 篇）:")
            for a in articles[:5]:
                print(f"  · {a['title'][:50]}")
            if count > 5:
                print(f"  ... 还有 {count - 5} 篇")
        else:
            print(f"本轮无新增（累计 {total} 篇）")

        elapsed = time.time() - start
        sleep_sec = max(0, interval * 60 - elapsed)
        next_time = datetime.now().timestamp() + sleep_sec
        print(f"耗时 {elapsed:.0f}s，下次 {datetime.fromtimestamp(next_time).strftime('%H:%M:%S')}")
        print()

        time.sleep(sleep_sec)


if __name__ == "__main__":
    main()
