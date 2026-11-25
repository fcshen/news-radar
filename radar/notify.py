"""推送：Bark / 企微 / 控制台。消息格式对齐频道式快讯。"""
import requests

from .score import TIER_LABEL
from .translate import display_title

LEVEL_ICON = {"L3": "🔴", "L2": "🟠", "L1": "⚪", "L0": "⚫"}


def _text(ev):
    """正文优先用中文摘要，没有才退回原文。"""
    s = (ev.get("summary") or "").strip()
    if s:
        return s.replace("\n", " ")[:220]
    body = (ev.get("body") or "").replace("\n", " ").strip()
    if body and body != ev.get("title"):
        return body[:200]
    return ""


def format_message(ev):
    lines = []
    txt = _text(ev)
    if txt:
        lines.append(txt)
        lines.append("")
    # 英文源补一行原文，便于核对与搜索
    if ev.get("lang") == "en" and ev.get("title_zh"):
        orig = (ev.get("title") or "").replace("\n", " ")[:120]
        lines.append(f"原文：{orig}")
        lines.append("")
    if ev.get("impact"):
        lines.append(f"影响（推断）：{ev['impact']}")
        lines.append("")
    if ev.get("alts"):
        lines.append("同组：" + "；".join(ev["alts"]))
        lines.append("")
    srcs = ev.get("sources") or [ev["source"]]
    extra = f" 等 {len(srcs)} 源" if len(srcs) > 1 else ""
    lines.append(f"来源：{ev['source']} · {TIER_LABEL.get(ev.get('tier'), ev.get('tier'))}{extra}")
    return "\n".join(lines)


def bark(cfg_notify, title, body, url="", level="L2"):
    conf = (cfg_notify or {}).get("bark") or {}
    if not conf.get("enabled") or not conf.get("url"):
        return False, "未配置 Bark"
    payload = {
        "title": title,
        "body": body,
        "group": conf.get("group", "金融雷达"),
    }
    if url:
        payload["url"] = url
    if level == "L3":
        payload["level"] = "timeSensitive"
        payload["sound"] = conf.get("level3_sound", "alarm")
    elif conf.get("sound"):
        payload["sound"] = conf["sound"]
    try:
        r = requests.post(conf["url"], json=payload, timeout=10)
        return r.ok, r.text[:120]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:120]


def push_event(cfg, ev, dry_run=False):
    icon = LEVEL_ICON.get(ev["level"], "")
    hm = ev.get("ts", "")[11:16]
    title = f"{icon} {hm} {display_title(ev)}"[:90]
    body = format_message(ev)
    if dry_run:
        print("\n--- [DRY-RUN 推送] ---")
        print(title)
        print(body)
        print(f"链接：{ev.get('url', '')}")
        return True
    ok, msg = bark(cfg.get("notify"), title, body, ev.get("url", ""), ev["level"])
    if not ok:
        print(f"[推送失败] {msg}")
    return ok


def push_digest(cfg, events, dry_run=False):
    if not events:
        return False
    events = sorted(events, key=lambda x: x["ts"])
    lines = [f"📋 摘要 · 共 {len(events)} 条", ""]
    for ev in events[-20:]:
        hm = ev.get("ts", "")[11:16]
        lines.append(f"{hm} 【{display_title(ev)[:38]}】{ev['source']}")
    body = "\n".join(lines)
    if dry_run:
        print("\n--- [DRY-RUN 摘要] ---")
        print(body)
        return True
    ok, msg = bark(cfg.get("notify"), f"📋 摘要 {len(events)} 条", body, "", "L1")
    if not ok:
        print(f"[摘要失败] {msg}")
    return ok
