"""推送：多通道串联，前一个失败自动换下一个。

为什么做成通道链：
单个推送服务（Bark 的服务器）不是永远可用，而"不漏"是这个软件的第一要求。
一次请求失败不应该等于一条永远收不到的消息。

三条硬约束：
1. 单通道最多等 timeout 秒（默认 3），不许把采集主循环卡住
2. 未配置的通道静默跳过，不算失败，也不触发冷却
3. 某通道刚失败过就进入冷却，避免接下来每条消息都先去坏通道上白等
"""
import base64
import time
from urllib.parse import quote

import requests

from .score import TIER_LABEL
from .translate import display_title

LEVEL_ICON = {"L3": "🔴", "L2": "🟠", "L1": "⚪", "L0": "⚫"}

DEFAULT_ORDER = ("bark", "wecom", "ntfy")
DEFAULT_TIMEOUT = 3.0          # 单通道等待上限（秒）
COOLDOWN_SEC = 90.0            # 通道失败后的冷却时长
DEFAULT_ENABLED = {"bark": True, "wecom": False, "ntfy": False}
LABEL = {"bark": "Bark", "wecom": "企业微信", "ntfy": "ntfy"}

_cool = {}                     # 通道名 -> 冷却到期时间戳


# ---------------------------------------------------------------- 内部工具
def _wait(timeout):
    """连接最多 1.6 秒，读取最多 timeout 秒。"""
    return (min(1.6, timeout), timeout)


def _cooling(ch):
    return _cool.get(ch, 0) > time.time()


def _mark_fail(ch):
    _cool[ch] = time.time() + COOLDOWN_SEC


def _mark_ok(ch):
    _cool.pop(ch, None)


def _rfc2047(s):
    """ntfy 的标题头只认 ASCII，中文要按 RFC 2047 编码。"""
    if not s:
        return ""
    try:
        s.encode("ascii")
        return s
    except UnicodeEncodeError:
        b = base64.b64encode(s.encode("utf-8")).decode("ascii")
        return f"=?UTF-8?B?{b}?="


# ---------------------------------------------------------------- 消息正文
def board_root(cfg):
    """看板根地址（notify.site）。没配就返回空串。"""
    site = ((cfg.get("notify") or {}).get("site") or "").strip()
    return site.rstrip("/") + "/" if site else ""


def board_link(cfg, ev):
    """通知点开落到看板并展开该条，而不是直接跳外媒。

    原因：英文源（Reuters/FT/日经）在国内不开 VPN 常打不开，
    点通知一片空白等于消息白推。落看板至少能看到中文摘要，
    要看原文再点卡片里的「原文 ↗」，多一步但一定打得通。
    """
    base = board_root(cfg)
    eid = str(ev.get("id") or "").strip()
    if base and eid:
        return base + "?e=" + quote(eid, safe="")
    return ev.get("url", "")


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


# ---------------------------------------------------------------- 各通道
def _send_bark(conf, title, body, url, level, timeout):
    """返回 True=送达 / False=失败 / None=没配置（跳过）"""
    if not conf.get("url"):
        return None, "未配置地址"
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
        r = requests.post(conf["url"], json=payload, timeout=_wait(timeout))
    except Exception as exc:
        return False, type(exc).__name__
    if not r.ok:
        return False, f"HTTP {r.status_code}"
    return True, "ok"


def _send_wecom(conf, title, body, url, level, timeout):
    hook = (conf.get("webhook") or "").strip()
    if not hook:
        return None, "未配置 webhook"
    md = f"**{LEVEL_ICON.get(level, '')} {title}**\n{body}"
    if url:
        md += f"\n[查看原文]({url})"
    payload = {"msgtype": "markdown", "markdown": {"content": md[:3800]}}
    try:
        r = requests.post(hook, json=payload, timeout=_wait(timeout))
        data = r.json() if r.content else {}
    except Exception as exc:
        return False, type(exc).__name__
    if r.ok and isinstance(data, dict) and data.get("errcode") == 0:
        return True, "ok"
    code = data.get("errcode") if isinstance(data, dict) else None
    return False, f"errcode={code if code is not None else r.status_code}"


def _send_ntfy(conf, title, body, url, level, timeout):
    topic = (conf.get("topic") or "").strip()
    if not topic:
        return None, "未配置频道"
    server = (conf.get("server") or "https://ntfy.sh").rstrip("/")
    headers = {
        "Title": _rfc2047(title),
        "Priority": {"L3": "5", "L2": "4"}.get(level, "3"),
        "Tags": "rotating_light" if level == "L3" else "warning",
    }
    if url:
        headers["Click"] = url
    try:
        r = requests.post(f"{server}/{topic}", data=body.encode("utf-8"),
                          headers=headers, timeout=_wait(timeout))
    except Exception as exc:
        return False, type(exc).__name__
    if not r.ok:
        return False, f"HTTP {r.status_code}"
    return True, "ok"


_SENDERS = {"bark": _send_bark, "wecom": _send_wecom, "ntfy": _send_ntfy}


# ---------------------------------------------------------------- 投递
def deliver(cfg, title, body, url="", level="L2"):
    """按通道链投递。返回 (是否送达, 用了哪个通道, 说明)。"""
    conf_all = cfg.get("notify") or {}
    order = [c for c in (conf_all.get("order") or DEFAULT_ORDER) if c in _SENDERS]
    try:
        timeout = float(conf_all.get("timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    timeout = max(0.5, min(timeout, 15.0))

    cands = []
    for ch in order:
        conf = conf_all.get(ch) or {}
        if not conf.get("enabled", DEFAULT_ENABLED.get(ch, False)):
            continue
        cands.append((ch, conf))
    if not cands:
        return False, "", "没有启用任何推送通道"

    # 冷却中的先让开；如果全都冷却，只能硬着头皮试（否则一条都发不出去）
    fresh = [c for c in cands if not _cooling(c[0])]

    notes = []
    for ch, conf in (fresh or cands):
        ok, detail = _SENDERS[ch](conf, title, body, url, level, timeout)
        if ok is None:                      # 未配置，跳过不算失败
            notes.append(f"{LABEL.get(ch, ch)}未配置")
            continue
        if ok:
            _mark_ok(ch)
            return True, ch, detail
        _mark_fail(ch)
        notes.append(f"{LABEL.get(ch, ch)}失败({detail})")
    return False, "", "；".join(notes)


def push_event(cfg, ev, dry_run=False):
    icon = LEVEL_ICON.get(ev["level"], "")
    hm = ev.get("ts", "")[11:16]
    title = f"{icon} {hm} {display_title(ev)}"[:90]
    body = format_message(ev)
    if dry_run:
        print("\n--- [DRY-RUN 推送] ---")
        print(title)
        print(body)
        print(f"点开：{board_link(cfg, ev)}")
        print(f"原文：{ev.get('url', '')}")
        return True
    ok, ch, detail = deliver(cfg, title, body, board_link(cfg, ev), ev["level"])
    if not ok:
        print(f"[推送失败] {detail}")
    elif ch != "bark":
        print(f"[推送] 主通道没走通，已由{LABEL.get(ch, ch)}送达")
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
    ok, ch, detail = deliver(cfg, f"📋 摘要 {len(events)} 条", body,
                             board_root(cfg), "L1")
    if not ok:
        print(f"[摘要失败] {detail}")
    elif ch != "bark":
        print(f"[摘要] 主通道没走通，已由{LABEL.get(ch, ch)}送达")
    return ok
