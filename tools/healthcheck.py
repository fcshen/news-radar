"""数据新鲜度检查：判断雷达是否停摆。

给 .github/workflows/watchdog.yml 用，也可以本地手动跑：
    python tools/healthcheck.py

输出是 GitHub Actions 的 key=value 格式，同时人看着也清楚。
"""
import datetime
import json
import sys
from pathlib import Path

# 35 分钟：正常情况下数据每 2 分钟一次提交，超过这个数基本可以断定停了。
# 留这么宽的余量是防 Actions 排队：偶尔一次构建慢十几分钟属正常。
STALE_MIN = 35
# 90 分钟：到这一步说明自动重启没救回来，必须让人知道。
ALERT_MIN = 90


def main() -> int:
    path = Path("data/feed.json")
    if not path.exists():
        print("mins=-1")
        print("stale=1")
        print("alert=1")
        print("total=0")
        print("reason=missing")
        return 0

    try:
        feed = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.datetime.fromisoformat(feed["generated"])
    except (ValueError, KeyError, OSError) as exc:
        print(f"mins=-1\nstale=1\nalert=1\ntotal=0\nreason={exc.__class__.__name__}")
        return 0

    now = datetime.datetime.now(generated.tzinfo)
    mins = int((now - generated).total_seconds() // 60)

    print(f"mins={mins}")
    print(f"stale={1 if mins > STALE_MIN else 0}")
    print(f"alert={1 if mins > ALERT_MIN else 0}")
    print(f"total={feed.get('total', 0)}")
    print(f"generated={feed.get('generated', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
