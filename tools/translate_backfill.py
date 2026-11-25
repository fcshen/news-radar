#!/usr/bin/env python3
"""给事件库里已有的英文条目补中文标题与摘要。

新采集的英文消息会在入库时自动翻译，这个工具用于补齐历史数据
（比如开启翻译功能之前入库的条目），也可以随时重跑，已翻过的会跳过。

注意：程序运行中执行会被内存中的旧数据覆盖，先停服务再跑。

用法：
  python tools/translate_backfill.py                补中文标题
  python tools/translate_backfill.py --body         连正文摘要一起补
  python tools/translate_backfill.py --data-dir xxx 指定目录
  python tools/translate_backfill.py --limit 50     最多补 50 条
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar import translate                      # noqa: E402
from radar.config import load_config             # noqa: E402
from radar.store import Store, now               # noqa: E402


def is_chinese(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--limit", type=int, default=0, help="最多处理多少条，0 为不限")
    ap.add_argument("--body", action="store_true",
                    help="同时补正文摘要（会把英文摘要换成中文，消耗更多免费额度）")
    args = ap.parse_args()

    cfg = load_config()
    store = Store(args.data_dir)
    cache = Path(args.data_dir) / "translate_cache.json"
    translate.load_cache(cache)

    today = now().strftime("%Y-%m-%d")

    # 一、补中文标题
    pending = [e for e in store.events
               if e.get("lang") == "en" and not e.get("title_zh")]
    pending.sort(key=lambda e: e.get("ts", ""), reverse=True)
    if args.limit:
        pending = pending[:args.limit]

    print(f"英文条目待补标题 {len(pending)} 条（库内共 {len(store.events)} 条）")
    done = 0
    for ev in pending:
        zh = translate.fill_title(ev, cfg, today=today)
        if zh:
            done += 1
            print(f"  ✓ {ev.get('ts', '')[5:16]} {zh[:36]}")
        else:
            print(f"  · {ev.get('ts', '')[5:16]} 未翻：{ev.get('title', '')[:40]}")
    print(f"标题补翻 {done}/{len(pending)}")

    # 二、补中文正文摘要（只处理该进摘要池以上的，省额度）
    if args.body:
        todo = [e for e in store.events
                if e.get("lang") == "en" and e.get("level") in ("L1", "L2", "L3")
                and not is_chinese(e.get("summary"))]
        todo.sort(key=lambda e: e.get("ts", ""), reverse=True)
        print(f"\n待补中文摘要 {len(todo)} 条")
        ok = 0
        for ev in todo:
            zh = translate.body_summary(ev, cfg, today=today)
            if zh:
                ev["summary"] = zh
                ok += 1
                print(f"  ✓ {ev.get('ts', '')[5:16]} {zh[:44]}")
            else:
                print(f"  · {ev.get('ts', '')[5:16]} 未翻")
        print(f"摘要补翻 {ok}/{len(todo)}")

    store.save_events()
    translate.save_cache(cache)
    print("\n完成。未翻的会保持原文，页面上会标注")


if __name__ == "__main__":
    main()
