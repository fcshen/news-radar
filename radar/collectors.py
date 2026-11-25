"""采集层：所有渠道统一输出 {title, body, url, ts, lang, key?}

新增渠道只需在 config.yaml 的 sources 里加一条。
"""
import gzip
import io
import json
import re
import time
from datetime import datetime, timedelta, timezone

import requests
import feedparser

from .dedupe import clean_text

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TZ = timezone(timedelta(hours=8))
TIMEOUT = 10

_session = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        adapter = requests.adapters.HTTPAdapter(max_retries=0, pool_maxsize=20)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _session = s
    return _session


def _get(url, **kw):
    kw.setdefault("timeout", TIMEOUT)
    r = session().get(url, **kw)
    r.raise_for_status()
    return r


def _parse_dt(text, fmt=None):
    """尽量宽容地解析各种时间格式，失败返回当前时间。"""
    if isinstance(text, datetime):
        return text if text.tzinfo else text.replace(tzinfo=TZ)
    if not text:
        return datetime.now(TZ)
    text = str(text).strip()
    candidates = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
    ]
    if fmt:
        candidates.insert(0, fmt)
    for f in candidates:
        try:
            dt = datetime.strptime(text, f)
            return dt if dt.tzinfo else dt.replace(tzinfo=TZ)
        except ValueError:
            continue
    for chop in (19, 16, 10):
        try:
            dt = datetime.strptime(text[:chop], "%Y-%m-%d" if chop == 10 else
                                   ("%Y-%m-%d %H:%M" if chop == 16 else "%Y-%m-%d %H:%M:%S"))
            return dt.replace(tzinfo=TZ)
        except ValueError:
            continue
    return datetime.now(TZ)


def split_title(text: str, limit=60):
    """中文快讯常见格式：【标题】正文。有就拆，没有就截取首句。"""
    text = clean_text(text)
    m = re.match(r"^[【\[](.*?)[】\]](.*)$", text, re.S)
    if m and m.group(1).strip():
        return m.group(1).strip()[:limit], m.group(2).strip()
    for sep in ("。", "！", "？", "；"):
        idx = text.find(sep)
        if 0 < idx <= limit:
            return text[:idx], text[idx + 1:].strip()
    return text[:limit], text[limit:].strip()


# ------------------------------------------------------------------
# 通用 RSS / Atom —— 覆盖国内外绝大多数媒体与官方机构
# ------------------------------------------------------------------
def fetch_rss(src, limit=30):
    url = src.get("url") or ""
    if not url:
        return []
    r = _get(url, headers={"Accept": "application/rss+xml, application/xml, text/xml, */*"})
    raw = r.content
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    feed = feedparser.parse(raw)
    items = []
    for e in feed.entries[:limit]:
        title = clean_text(e.get("title", ""))
        body = clean_text(e.get("summary", "") or e.get("description", ""))
        if not title and not body:
            continue
        ts = None
        for k in ("published_parsed", "updated_parsed", "created_parsed"):
            if e.get(k):
                ts = datetime(*e[k][:6], tzinfo=timezone.utc).astimezone(TZ)
                break
        if ts is None:
            ts = _parse_dt(e.get("published", ""))
        if not title:
            title, body = split_title(body)
        items.append({
            "title": title[:200],
            "body": body[:1200],
            "url": e.get("link", ""),
            "ts": ts,
            "lang": "en" if _looks_en(title) else "zh",
        })
    return items


def _looks_en(text: str) -> bool:
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    return en > zh * 2 and en > 10


# ------------------------------------------------------------------
# 新浪财经 7×24
# ------------------------------------------------------------------
def fetch_sina(src, limit=30):
    url = ("https://zhibo.sina.com.cn/api/zhibo/feed"
           f"?zhibo_id=152&page=1&page_size={limit}&tag_id=0&dire=f&dpc=1")
    data = _get(url).json()
    entries = (((data.get("result") or {}).get("data") or {}).get("feed") or {}).get("list") or []
    items = []
    for e in entries[:limit]:
        text = clean_text(e.get("rich_text", ""))
        if not text:
            continue
        title, body = split_title(text)
        items.append({
            "title": title,
            "body": body or text,
            "url": e.get("docurl") or f"https://finance.sina.com.cn/7x24/",
            "ts": _parse_dt(e.get("create_time")),
            "lang": "zh",
        })
    return items


# ------------------------------------------------------------------
# 金十数据（期货与宏观强）
# ------------------------------------------------------------------
def fetch_jin10(src, limit=30):
    url = "https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1"
    r = _get(url, headers={"x-app-id": "bVBF4FyRTn5NJF5n", "x-version": "1.0.0"})
    data = r.json()
    items = []
    for e in (data.get("data") or [])[:limit]:
        d = e.get("data") or {}
        text = clean_text(d.get("content") or d.get("title") or "")
        if not text:
            continue
        title, body = split_title(text)
        items.append({
            "title": title,
            "body": body or text,
            "url": d.get("link") or "https://www.jin10.com/",
            "ts": _parse_dt(e.get("time")),
            "lang": "zh",
        })
    return items


# ------------------------------------------------------------------
# 深交所公告（一手）
# ------------------------------------------------------------------
def fetch_szse(src, limit=40):
    today = datetime.now(TZ)
    start = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    body = {
        "seDate": [start, end],
        "channelCode": ["listedNotice_disc"],
        "pageSize": limit,
        "pageNum": 1,
    }
    r = session().post(
        "https://www.szse.cn/api/disc/announcement/annList?random=0.1",
        json=body, timeout=TIMEOUT,
        headers={"Content-Type": "application/json",
                 "Referer": "https://www.szse.cn/disclosure/listed/notice/"},
    )
    r.raise_for_status()
    data = r.json()
    items = []
    for e in (data.get("data") or [])[:limit]:
        title = e.get("title") or ""
        codes = e.get("secCode") or []
        names = e.get("secName") or []
        prefix = f"{names[0]}({codes[0]})：" if names and codes else ""
        path = e.get("attachPath") or ""
        items.append({
            "title": (prefix + title)[:200],
            "body": f"{prefix}{title}",
            "url": f"https://disc.szse.cn/download{path}" if path else "https://www.szse.cn/disclosure/listed/notice/",
            "ts": _parse_dt(e.get("publishTime")),
            "lang": "zh",
        })
    return items


# ------------------------------------------------------------------
# Telegram 公开频道（t.me/s/ 网页预览，无需 API）
# ------------------------------------------------------------------
def fetch_telegram(src, limit=30):
    channel = (src.get("channel") or "").strip().lstrip("@")
    if not channel:
        return []
    r = _get(f"https://t.me/s/{channel}", timeout=15)
    html = r.text
    blocks = re.split(r'<div class="tgme_widget_message[ "]', html)[1:]
    items = []
    for b in blocks[:limit]:
        post = re.search(r'data-post="([^"]+)"', b)
        tm = re.search(r'<time[^>]*datetime="([^"]+)"', b)
        txt = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', b, re.S)
        if not txt:
            continue
        text = clean_text(txt.group(1))
        if len(text) < 8:
            continue
        title, body = split_title(text)
        items.append({
            "title": title,
            "body": body or text,
            "url": f"https://t.me/{post.group(1)}" if post else f"https://t.me/{channel}",
            "ts": _parse_dt(tm.group(1)) if tm else datetime.now(TZ),
            "lang": "zh" if not _looks_en(text) else "en",
        })
    return items


# ------------------------------------------------------------------
# 行情异动（触发式，不是新闻）
# ------------------------------------------------------------------
def fetch_quote(src, limit=20):
    codes = src.get("codes") or []
    if not codes:
        return []
    threshold = float(src.get("move_threshold", 1.2))
    r = _get("https://hq.sinajs.cn/list=" + ",".join(codes),
             headers={"Referer": "https://finance.sina.com.cn/"})
    r.encoding = "gbk"
    today = datetime.now(TZ).strftime("%Y%m%d")
    items = []
    for line in r.text.split(";"):
        m = re.search(r'hq_str_(\w+)="([^"]*)"', line)
        if not m:
            continue
        code, payload = m.group(1), m.group(2)
        f = payload.split(",")
        if len(f) < 4:
            continue
        try:
            name = f[0]
            prev, cur = float(f[2]), float(f[3])
            if prev <= 0 or cur <= 0:
                continue
            pct = (cur - prev) / prev * 100
        except (ValueError, IndexError):
            continue
        band = int(abs(pct) // threshold)
        if band < 1:
            continue
        sign = "+" if pct > 0 else "-"
        key = f"quote:{code}:{today}:{sign}{band}"
        items.append({
            "title": f"{name} {pct:+.2f}% 报 {cur:.2f}",
            "body": f"{name}（{code}）当前 {cur:.2f}，涨跌幅 {pct:+.2f}%，触及 ±{threshold*band:.1f}% 档位。",
            "url": f"https://finance.sina.com.cn/realstock/company/{code}/nc.shtml",
            "ts": datetime.now(TZ),
            "lang": "zh",
            "key": key,
        })
    return items


DISPATCH = {
    "rss": fetch_rss,
    "sina": fetch_sina,
    "jin10": fetch_jin10,
    "szse": fetch_szse,
    "telegram": fetch_telegram,
    "quote": fetch_quote,
}


def collect(src):
    fn = DISPATCH.get(src.get("type", "rss"))
    if not fn:
        return [], f"未知类型 {src.get('type')}"
    try:
        t0 = time.time()
        items = fn(src)
        return items, f"{len(items)} 条 / {time.time()-t0:.1f}s"
    except Exception as exc:  # 单源失败不影响整体
        return [], f"失败 {type(exc).__name__}: {str(exc)[:80]}"
