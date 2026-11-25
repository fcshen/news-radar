#!/usr/bin/env python3
"""对照工具：拿同一批历史数据，重放新打分与聚类，输出前后差异。

用法：python tools/compare.py [data/events.json]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from radar.dedupe import find_cluster_by_title, simhash
from radar.score import TIER_LABEL, evaluate

LV_ORDER = {"L3": 3, "L2": 2, "L1": 1, "L0": 0}


def load_cfg():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def replay(events, cfg):
    """按时间顺序重跑聚类 + 打分，返回新的事件簇列表。"""
    events = sorted(events, key=lambda e: e.get("ts", ""))
    pool, by_cid, clusters = [], {}, []
    quote_win = {}

    for e in events:
        ev = dict(e)
        cid = find_cluster_by_title(ev["title"], pool)
        if cid:
            host = by_cid[cid]
            if ev["source"] not in host["sources"]:
                host["sources"].append(ev["source"])
            host["_merged"].append(ev["title"])
            score, level, reason = evaluate(host, cfg, len(host["sources"]))
            host["score"], host["level"], host["reason"] = score, level, reason
            continue

        ev["cluster_id"] = ev.get("cluster_id", "")[:12]
        ev["sources"] = [ev["source"]]
        ev["_merged"] = []
        ev["_old_score"] = ev.get("score")
        ev["_old_level"] = ev.get("level")

        # 行情异动：10 分钟窗口内合并成一条
        if ev.get("channel") == "quote":
            wk = _qk(ev.get("ts", ""))
            host = quote_win.get(wk)
            if host is not None:
                host["alts"] = (host.get("alts") or []) + [ev["title"]]
                host["_merged"].append(ev["title"] + "（同组异动）")
                ev["_old_score"] = ev.get("score")
                ev["_old_level"] = "L2"
                ev["score"], ev["level"] = 0.0, "L0"
                ev["_dropped"] = True
                clusters.append(ev)
                continue
            quote_win[wk] = ev

        score, level, reason = evaluate(ev, cfg, 1)
        ev["score"], ev["level"], ev["reason"] = score, level, reason
        ev["sh"] = simhash(ev["title"])
        pool.append((ev["cluster_id"], ev["sh"], ev["title"]))
        by_cid[ev["cluster_id"]] = ev
        clusters.append(ev)

    return clusters


def _qk(ts):
    if len(ts) < 16:
        return ts[:14]
    try:
        b = int(ts[14:16]) // 10
    except ValueError:
        b = 0
    return f"{ts[:14]}{b}"


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "events.json"
    events = json.load(open(path, encoding="utf-8"))
    cfg = load_cfg()
    push_th = cfg["thresholds"]["push"]
    digest_th = cfg["thresholds"]["digest"]

    clusters = replay(events, cfg)
    kept = [c for c in clusters if not c.get("_dropped")]
    old_push = [e for e in events if e.get("pushed")]

    print("=" * 74)
    print(f"原始入库 {len(events)} 条  →  聚类合并后 {len(kept)} 个事件")
    print(f"合并掉 {len(events) - len(kept)} 条重复/同组异动 | "
          f"阈值 推送≥{push_th} 摘要≥{digest_th}")
    print("=" * 74)

    print("\n【会推送到手机的】")
    hot = [c for c in kept if c["level"] in ("L2", "L3") and c["score"] >= push_th]
    hot.sort(key=lambda c: -c["score"])
    if not hot:
        print("  （无）")
    for i, c in enumerate(hot, 1):
        print(f"  {i}. [{c['level']}] {c['score']:.1f}  {c['title'][:52]}")
        print(f"     来源：{c['source']} · {TIER_LABEL.get(c.get('tier'))}"
              + (f"（{len(c['sources'])} 源）" if len(c["sources"]) > 1 else ""))
        if c["_merged"]:
            for m in c["_merged"]:
                print(f"     并：{m[:56]}")

    print("\n【进摘要的】")
    mid = [c for c in kept
           if c["level"] == "L1" and c["score"] >= digest_th]
    mid.sort(key=lambda c: -c["score"])
    for c in mid:
        print(f"  · {c['score']:.1f}  {c['title'][:56]}")

    print("\n【升级的（原 L0 → 现 L1/L2）】")
    up = [c for c in kept
          if LV_ORDER[c["level"]] > LV_ORDER.get(c["_old_level"], 0)]
    up.sort(key=lambda c: -c["score"])
    for c in up:
        print(f"  {c['_old_score']:5.1f}{c['_old_level']} → {c['score']:5.1f}{c['level']}"
              f"  {c['title'][:44]}")
        print(f"        {c['reason']}")

    print("\n【降级的】")
    down = [c for c in kept
            if LV_ORDER[c["level"]] < LV_ORDER.get(c["_old_level"], 0)]
    down.sort(key=lambda c: c["score"])
    for c in down:
        print(f"  {c['_old_score']:5.1f}{c['_old_level']} → {c['score']:5.1f}{c['level']}"
              f"  {c['title'][:44]}")

    print("\n【汇总】")
    from collections import Counter
    print("  旧级别:", dict(Counter(e.get("level") for e in events)))
    print("  新级别:", dict(Counter(c["level"] for c in kept)))
    print(f"  旧推送 {len(old_push)} 条 → 新推送 {len(hot)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
