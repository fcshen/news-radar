#!/usr/bin/env python3
"""金融事件雷达 · 入口

用法：
  python main.py --once              跑一轮就退出（调试用）
  python main.py --once --dry-run    跑一轮，只打印不推送
  python main.py                     长驻轮询（云端 / 电脑端）
  python main.py --minutes 350       跑 350 分钟后自动退出（GitHub Actions 用）
"""
import argparse
import signal
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from radar import ai as ai_mod
from radar import collectors, notify, translate
from radar.config import load_config
from radar.dedupe import fingerprint, simhash, find_cluster_by_title
from radar.score import apply_score
from radar.store import Store, make_event, now, iso

ROOT = Path(__file__).resolve().parent
STOP = False


def _today_key():
    """翻译额度按日计，跨零点自动重置。"""
    return now().strftime("%Y-%m-%d")


def _cache_path(data_dir):
    return Path(data_dir) / "translate_cache.json"


def _sigterm(_sig, _frm):
    global STOP
    STOP = True


try:                       # 被 app.py 以线程方式调用时，主线程之外不能注册信号
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)
except ValueError:
    pass


def active_sources(cfg):
    return [s for s in cfg.get("sources", []) if s.get("enabled", True)]


def in_quiet_hours(cfg, dt=None):
    q = (cfg.get("notify") or {}).get("quiet_hours") or {}
    if not q.get("enabled"):
        return False
    dt = dt or now()
    cur = dt.hour * 60 + dt.minute
    start = _hhmm(q.get("start", "23:30"))
    end = _hhmm(q.get("end", "07:00"))
    return (start <= cur or cur < end) if start > end else (start <= cur < end)


def _hhmm(text):
    try:
        h, m = text.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def build_event(item, src):
    return make_event(
        title=item["title"],
        body=item.get("body", ""),
        url=item.get("url", ""),
        ts=item.get("ts") or now(),
        source=src["name"],
        tier=src.get("tier", "media"),
        region=src.get("region", "cn"),
        lang=item.get("lang", "zh"),
        channel=src.get("type", "rss"),
    )


def _quote_key(ts):
    """行情异动按 10 分钟分桶：同一时段的多品种异动合成一条。"""
    ts = ts or ""
    if len(ts) < 16:
        return ts[:14]
    try:
        bucket = int(ts[14:16]) // 10
    except ValueError:
        bucket = 0
    return f"{ts[:14]}{bucket}"


def run_round(cfg, store, dry_run=False, verbose=True):
    """抓一轮，返回 (新增数, 推送数)。"""
    srcs = active_sources(cfg)
    results = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(srcs)))) as pool:
        futures = {pool.submit(collectors.collect, s): s for s in srcs}
        for fut in futures:
            src = futures[fut]
            try:
                items, status = fut.result(timeout=60)
            except Exception as exc:
                items, status = [], f"超时 {type(exc).__name__}"
            results.append((src, items, status))
            if verbose:
                flag = "✓" if items else "·"
                print(f"  {flag} {src['name']:<14} {status}")

    # 近期事件构成聚类池（带标题，用于标题相似度判定）
    recent = store.recent(240)
    cluster_pool = [(e["cluster_id"], e.get("sh", 0), e["title"])
                    for e in recent if e.get("sh")]
    by_cluster = {e["cluster_id"]: e for e in recent}

    # 行情异动：10 分钟窗口内只推一条
    quote_win = {}
    for e in recent:
        if e.get("channel") == "quote":
            quote_win[_quote_key(e.get("ts", ""))] = e["cluster_id"]

    backfill = int(cfg.get("runtime", {}).get("backfill_minutes", 120))
    cutoff = now() - timedelta(minutes=backfill)
    new_events, push_queue = [], []
    queued = set()          # 本轮已排队的 id，防止同一事件重复入队
    skipped_old = 0

    for src, items, _ in results:
        for item in items[:40]:
            ts = item.get("ts")
            if ts is not None and ts < cutoff:
                skipped_old += 1        # RSS 里的历史文章，不当新消息
                continue
            key = item.get("key")
            fp = fingerprint(item["title"], item.get("body", ""))
            if key:
                fp = key
            if store.has_seen(fp):
                continue
            store.mark_seen(fp)

            ev = build_event(item, src)
            # 英文消息先补中文标题：看板、摘要、推送都用得上。
            # 失败不阻塞入库，只保留原文 + EN 标记。
            if ev.get("lang") == "en":
                try:
                    translate.fill_title(ev, cfg, today=_today_key())
                except Exception:
                    pass
            sh = simhash(ev["title"])
            ev["sh"] = sh

            # 同一事件：标题相似度判定（不再只比前 14 字）
            cid = find_cluster_by_title(ev["title"], cluster_pool)
            if cid:
                host = by_cluster.get(cid)
                if host:
                    if ev["source"] not in host["sources"]:
                        host["sources"].append(ev["source"])
                    apply_score(host, cfg, source_count=len(host["sources"]))
                    if (not host.get("pushed") and host["level"] in ("L2", "L3")
                            and host["score"] >= cfg["thresholds"]["push"]
                            and host["id"] not in queued):
                        queued.add(host["id"])
                        push_queue.append(host)
                continue

            ev["cluster_id"] = fp[:12]
            apply_score(ev, cfg, source_count=1)

            # 行情异动：并入同一 10 分钟窗口的首条，不重复推
            if ev["channel"] == "quote":
                wk = _quote_key(ev["ts"])
                host_cid = quote_win.get(wk)
                host = by_cluster.get(host_cid)
                if host:
                    host["alts"] = (host.get("alts") or []) + [ev["title"]]
                    continue
                quote_win[wk] = ev["cluster_id"]

            cluster_pool.append((ev["cluster_id"], sh, ev["title"]))
            by_cluster[ev["cluster_id"]] = ev
            new_events.append(ev)

            if ev["level"] in ("L2", "L3"):
                if in_quiet_hours(cfg) and ev["level"] == "L2":
                    continue           # 静默时段暂不推；静默结束后由补推兜住
                if ev["id"] not in queued:
                    queued.add(ev["id"])
                    push_queue.append(ev)

    # 所有新事件统一做 AI 中文摘要（智谱 glm-4-flash 免费线路，三层降级）。
    # 看板、摘要、推送共用同一份结果，避免各写各的。
    # 并发调用，避免一轮几十条串行拖垮采集节奏；并发上限保守，防止触发限流。
    def _summarize_one(ev):
        title_zh, summary, impact, engine = ai_mod.summarize(ev, cfg)
        if engine and engine not in ("off",):
            ev["engine"] = engine
        # AI 给的标题比机翻准，优先覆盖；机翻结果留着兜底
        if title_zh:
            if ev.get("lang") == "en":
                ev["title_zh"] = title_zh
            elif not ev.get("title_zh"):
                ev["title_zh"] = title_zh
        # 无 AI 时英文正文用机翻兜底，入库阶段若已补过就直接沿用
        if not summary and ev.get("lang") == "en":
            summary = ev.get("summary") or translate.body_summary(
                ev, cfg, today=_today_key())
        if summary:
            ev["summary"] = summary
        if impact:
            ev["impact"] = impact
        return ev

    if new_events:
        # 智谱 glm-4-flash 免费档并发限制低（免费用户约 2 并发），
        # 并发过高会触发 429 限流，反而导致更多请求降级到本地兜底。
        workers = min(2, max(1, len(new_events)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for _ in pool.map(_summarize_one, new_events):
                pass

    added = store.add_events(new_events)
    pushed = 0

    for ev in push_queue:
        if ev["level"] == "L0":
            continue
        ev["tries"] = int(ev.get("tries", 0)) + 1
        if notify.push_event(cfg, ev, dry_run=dry_run):
            ev["pushed"] = True      # 只有真的送达才置位；失败留给下一轮补推
            pushed += 1

    pushed += sweep_unpushed(cfg, store, dry_run=dry_run)

    return added, pushed, results, skipped_old


def sweep_unpushed(cfg, store, dry_run=False, limit=6):
    """补推兜底：把「推送失败」和「静默时段压住」的 L2/L3 再送一次。

    没有这一步，一次网络抖动就会让一条重大事件永久静默——这是「不漏」的洞。
    """
    if in_quiet_hours(cfg):
        return 0
    rt = cfg.get("runtime") or {}
    win = int(rt.get("retry_minutes", 90))
    max_tries = int(rt.get("retry_max", 3))
    cutoff = iso(now() - timedelta(minutes=win))

    cand = [e for e in store.recent(win)
            if e.get("level") in ("L2", "L3")
            and not e.get("pushed")
            and e.get("ts", "") >= cutoff
            and int(e.get("tries", 0)) < max_tries]
    if not cand:
        return 0
    cand.sort(key=lambda x: x["ts"])

    sent = 0
    for ev in cand[:limit]:
        ev["tries"] = int(ev.get("tries", 0)) + 1
        if notify.push_event(cfg, ev, dry_run=dry_run):
            ev["pushed"] = True
            sent += 1
        else:
            break                    # 通道整体不通，这一轮别再硬打
    if sent:
        print(f"  → 补推 {sent} 条（此前未送达）")
    return sent


def send_digest(cfg, store, dry_run=False, verbose=True):
    pool = [e for e in store.recent(24 * 60) if e["level"] == "L1" and not e.get("pushed")]
    if not pool:
        return 0
    # 摘要里英文消息也要中文：能调 AI 就用 AI，否则机翻标题
    today = _today_key()
    for ev in pool:
        if ev.get("lang") == "en" and not ev.get("title_zh"):
            translate.fill_title(ev, cfg, today=today)
    ok = notify.push_digest(cfg, pool, dry_run=dry_run)
    if ok:
        for e in pool:
            e["pushed"] = True
    if verbose:
        print(f"  → 摘要推送 {len(pool)} 条")
    return len(pool)


def run(minutes=0, dry_run=False, data_dir=None, once=False, on_round=None):
    """采集主循环。app.py 与命令行共用，返回退出码。"""
    cfg = load_config()
    rt = cfg.get("runtime", {})
    poll = int(rt.get("poll_seconds", 30))
    max_minutes = minutes or int(rt.get("max_run_minutes", 350))

    store = Store(data_dir or (ROOT / "data"))
    translate.load_cache(_cache_path(store.dir))
    deadline = now() + timedelta(minutes=max_minutes)

    try:
        from zoneinfo import ZoneInfo
        tzname = rt.get("timezone", "Asia/Shanghai")
        deadline = datetime.now(ZoneInfo(tzname)) + timedelta(minutes=max_minutes)
    except Exception:
        tzname = "Asia/Shanghai"

    print(f"[{now():%H:%M:%S}] 启动采集 · 源 {len(active_sources(cfg))} 个 · "
          f"轮询 {poll}s · 最长 {max_minutes}min · dry_run={dry_run}")

    # 回溯：首轮直接跑，后续按间隔
    next_due = {s["name"]: now() for s in active_sources(cfg)}
    last_digest = now()
    rounds = 0

    while not STOP:
        cur = now()
        if cur >= deadline:
            print(f"[{cur:%H:%M:%S}] 到达运行时限，正常退出")
            break

        due = [s for s in active_sources(cfg)
               if next_due.get(s["name"], cur) <= cur]
        if due:
            rounds += 1
            print(f"\n[{cur:%H:%M:%S}] 第 {rounds} 轮 · {len(due)} 个源到期")
            try:
                added, pushed, _, skipped = run_round(cfg, store, dry_run=dry_run)
                print(f"  → 新增 {added} · 推送 {pushed} · 跳过旧条目 {skipped}")
                store.save_all()
                if on_round:
                    on_round(added, pushed, len(store.events))
            except Exception:
                traceback.print_exc()
            for s in due:
                next_due[s["name"]] = now() + timedelta(
                    seconds=int(s.get("interval", 60)))

        if (now() - last_digest) >= timedelta(hours=1):
            try:
                send_digest(cfg, store, dry_run=dry_run)
                store.save_events()
            except Exception:
                traceback.print_exc()
            last_digest = now()

        if once:
            break
        time.sleep(min(poll, 5))

    store.save_all()
    translate.save_cache(_cache_path(store.dir))
    print(f"[{now():%H:%M:%S}] 已退出，事件库 {len(store.events)} 条")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="只跑一轮")
    ap.add_argument("--minutes", type=int, default=0, help="运行多少分钟后退出")
    ap.add_argument("--dry-run", action="store_true", help="不推送，只打印")
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()
    return run(minutes=args.minutes, dry_run=args.dry_run,
               data_dir=args.data_dir, once=args.once)


if __name__ == "__main__":
    sys.exit(main())
