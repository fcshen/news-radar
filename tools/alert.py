"""用现有 Bark 地址推一条告警。没配 BARK_URL 就安静退出，不影响流程。

    python tools/alert.py "标题" "正文"
"""
import os
import sys
import urllib.parse
import urllib.request


def main() -> int:
    base = (os.environ.get("BARK_URL") or "").strip().rstrip("/")
    if not base:
        print("未配置 BARK_URL，跳过告警")
        return 0

    title = sys.argv[1] if len(sys.argv) > 1 else "雷达告警"
    body = sys.argv[2] if len(sys.argv) > 2 else ""

    # 路径里的中文必须编码，否则 Bark 端会 404
    url = "{}/{}/{}?{}".format(
        base,
        urllib.parse.quote(title, safe=""),
        urllib.parse.quote(body, safe=""),
        urllib.parse.urlencode({"group": "金融雷达", "level": "timeSensitive"}),
    )

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            print("告警已发送", resp.status)
    except Exception as exc:  # 告警失败绝不能反过来把任务搞挂
        print("告警发送失败：", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
