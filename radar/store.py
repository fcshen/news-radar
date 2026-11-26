"""存储层：JSON 文件即数据库，原子写入，支持并发安全。"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def is_future(ts, slack_minutes: int = 10) -> bool:
    """时间在未来的条目。

    为什么需要：联邦公报（Federal Register）这类源的发布时间是文档的
    公开/生效日，会比现在晚一天。这种"还没发生"的条目如果照常入库，
    会按时间倒序长期霸占列表头部，还会被当成突发消息推送出去。
    """
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt > now() + timedelta(minutes=slack_minutes)


def atomic_write(path: Path, data, compact: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if compact:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


class Store:
    def __init__(self, data_dir="data", keep_days=30):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.json"
        self.feed_path = self.dir / "feed.json"
        self.seen_path = self.dir / "seen.json"
        self.keep_days = keep_days
        self.events = read_json(self.events_path, [])
        self.seen = read_json(self.seen_path, {})

    # ---------- 事件 ----------
    def add_events(self, new_events):
        """按 id 去重追加，返回真正新增的条数。"""
        known = {e["id"] for e in self.events}
        added = 0
        for e in new_events:
            if e["id"] not in known:
                self.events.append(e)
                known.add(e["id"])
                added += 1
        if added:
            self.events.sort(key=lambda x: x["ts"], reverse=True)
            self._trim()
        return added

    def recent(self, minutes=180):
        cutoff = iso(now() - timedelta(minutes=minutes))
        return [e for e in self.events if e["ts"] >= cutoff]

    def _trim(self):
        cutoff = iso(now() - timedelta(days=self.keep_days))
        self.events = [e for e in self.events if e["ts"] >= cutoff][:20000]

    def save_events(self):
        atomic_write(self.events_path, self.events)
        self.save_feed()

    # ---------- 前端轻量数据 ----------
    # 手机端首屏只需要最近若干条 + 展示必需的字段。events.json 是全量归档
    # （900+ 条、约 900KB），在移动网络下首屏要等十几秒，故另出一份精简版。
    FEED_FIELDS = ("id", "ts", "title", "title_zh", "summary", "url", "source",
                   "tier", "region", "lang", "level", "impact", "alts")
    FEED_LIMIT = 300
    BODY_CAP = 220

    def build_feed(self, limit=None):
        limit = limit or self.FEED_LIMIT
        # 过滤掉"时间还没到"的条目：历史里已混入过联邦公报的预发布文档，
        # 不清掉就会长期占着前 300 条窗口，把真正的最新消息挤出去。
        rows = [e for e in self.events if not is_future(e.get("ts"))][:limit]
        out = []
        for e in rows:
            item = {k: e[k] for k in self.FEED_FIELDS
                    if e.get(k) not in (None, "", [])}
            body = (e.get("body") or "").strip()
            if body:
                item["body"] = body[: self.BODY_CAP]
            srcs = e.get("sources") or []
            if len(srcs) > 1:          # 只有一个来源时不重复写
                item["sources"] = srcs
            out.append(item)
        return {"total": len(self.events), "generated": iso(now()), "events": out}

    def save_feed(self):
        atomic_write(self.feed_path, self.build_feed(), compact=True)

    # ---------- 指纹 ----------
    def has_seen(self, fp):
        return fp in self.seen

    def mark_seen(self, fp):
        self.seen[fp] = iso(now())

    def mark_many(self, fps):
        for fp in fps:
            self.mark_seen(fp)

    def save_seen(self, keep_days=7):
        cutoff = iso(now() - timedelta(days=keep_days))
        self.seen = {k: v for k, v in self.seen.items() if v >= cutoff}
        atomic_write(self.seen_path, self.seen)

    def save_all(self):
        self.save_events()
        self.save_seen()


def make_event(*, title, body, url, ts, source, tier, region,
               lang="zh", channel="rss", score=0, level="L0",
               impact="", cluster_id="", sources=None):
    fp = f"{source}|{title}"[:200]
    import hashlib
    eid = hashlib.md5(fp.encode("utf-8")).hexdigest()[:16]
    return {
        "id": eid,
        "ts": iso(ts),
        "title": title.strip(),
        "title_zh": "",          # 英文源的中文标题，由翻译层填充
        "body": (body or "").strip(),
        "summary": "",           # AI 中文摘要，不覆盖 body，保留原文可回溯
        "url": url or "",
        "source": source,
        "tier": tier,
        "region": region,
        "lang": lang,
        "channel": channel,
        "score": score,
        "level": level,
        "impact": impact,
        "cluster_id": cluster_id,
        "sources": sources or [source],
        "pushed": False,
    }
