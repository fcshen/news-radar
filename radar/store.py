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


def atomic_write(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
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
