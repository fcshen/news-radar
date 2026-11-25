#!/usr/bin/env python3
"""源健康检查：把所有启用的渠道跑一遍，报告可用性与延迟。

用法：python tools/health.py
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from radar import collectors


def main():
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
    srcs = [s for s in cfg.get("sources", []) if s.get("enabled", True)]

    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(collectors.collect, s): s for s in srcs}
        for fut, s in futs.items():
            try:
                items, status = fut.result(timeout=60)
            except Exception as exc:
                items, status = [], f"异常 {type(exc).__name__}"
            rows.append((bool(items), s["name"], s.get("region", ""),
                         s.get("tier", ""), status))

    rows.sort(key=lambda r: (not r[0], r[1]))
    ok = sum(1 for r in rows if r[0])
    print(f"渠道 {len(rows)} 个 · 可用 {ok} · 失败 {len(rows) - ok}\n")

    print("【失败】")
    bad = [r for r in rows if not r[0]]
    if not bad:
        print("  （无）")
    for good, name, region, tier, status in bad:
        print(f"  ✗ {name:<18} {region:<5} {status[:74]}")

    print("\n【可用】")
    for good, name, region, tier, status in rows:
        if good:
            print(f"  ✓ {name:<18} {region:<5} {status}")

    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
