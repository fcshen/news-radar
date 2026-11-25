"""英文消息转中文。

三级降级，任何一层失效都不影响采集与推送：
  1. AI（GLM-4-Flash 等免费模型）—— 与摘要合并调用，质量最好，零额外成本
  2. MyMemory 免费接口 —— 无 key 时兜底，只翻标题，单次限 500 字符
  3. 原文 —— 前两层都不可用就保留英文，加 EN 标记

翻译结果按标题哈希缓存到 data/translate_cache.json，同一条不重复翻。
"""
import hashlib
import json
import re
import threading
import time
from pathlib import Path

import requests

MYMEMORY = "https://api.mymemory.translated.net/get"
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")}

# MyMemory 单次上限 500 字符，留余量
MAX_LEN = 450

_lock = threading.Lock()
_mem = {}          # 进程内缓存 {hash: 译文}
_day_count = {"date": "", "n": 0}
_exhausted = {"on": False, "date": ""}   # 接口明确回报额度耗尽


def _h(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def load_cache(path):
    global _mem
    p = Path(path)
    if p.exists():
        try:
            _mem = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _mem = {}
    # 每日额度计数也持久化：云端每几小时重启一次，内存计数会归零导致超额
    meta = _mem.pop("__meta__", None)
    if isinstance(meta, dict):
        _day_count["date"] = str(meta.get("date", ""))
        _day_count["n"] = int(meta.get("n", 0) or 0)
    return _mem


def save_cache(path, keep=3000):
    """落盘缓存。只保留最近 keep 条，避免文件随运行时间无限膨胀。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        items = list(_mem.items())[-keep:]
        snapshot = dict(items)
        snapshot["__meta__"] = {"date": _day_count["date"], "n": _day_count["n"]}
    try:
        p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass


def _quota_left(cfg, today):
    """每日免费额度计数，防止把 MyMemory 打到 429。"""
    limit = int((cfg.get("translate") or {}).get("free_daily_limit", 150))
    if _day_count["date"] != today:
        _day_count["date"] = today
        _day_count["n"] = 0
        _exhausted["on"] = False
    if _exhausted["on"] and _exhausted["date"] == today:
        return False
    return _day_count["n"] < limit


def _q(text):
    return re.sub(r"\s+", " ", (text or "")).strip()[:MAX_LEN]


def mymemory(text, timeout=12, retries=2):
    """MyMemory 免费翻译，失败重试，仍失败返回空串。

    这个接口偶发返回空或错误串（同一条重试即成功），所以必须带重试，
    否则每天会有几%的英文标题漏翻。
    """
    q = _q(text)
    if len(q) < 2:
        return ""
    for attempt in range(retries):
        try:
            r = requests.get(MYMEMORY,
                             params={"q": q, "langpair": "en|zh-CN"},
                             headers=UA, timeout=timeout)
            d = r.json()
            if d.get("quotaFinished"):
                _exhausted["on"] = True
                _exhausted["date"] = _day_count["date"]
                return ""
            t = (d.get("responseData") or {}).get("translatedText") or ""
            t = t.strip()
            # 接口出错时会把错误信息当译文返回。用关键词识别，不要用 isupper()：
            # "核心CPI指标".isupper() 是 True（只有大写字母没有小写），会误伤正常译文。
            bad = (not t
                   or "QUERY LENGTH" in t.upper()
                   or "MYMEMORY WARNING" in t.upper()
                   or "INVALID" in t.upper()
                   or "NO QUERY" in t.upper())
            if not bad and any("\u4e00" <= ch <= "\u9fff" for ch in t):
                return t
        except Exception:
            pass
        if attempt + 1 < retries:
            time.sleep(0.8)
    return ""


def to_zh(text, cfg, today="", use_free=True):
    """把一段英文翻成中文。命中缓存直接返回。"""
    if not text or not text.strip():
        return ""
    key = _h(text)
    cached = _mem.get(key)
    if cached:
        return cached
    if not use_free:
        return ""
    if today and not _quota_left(cfg, today):
        return ""

    zh = mymemory(text)
    if zh:
        with _lock:
            _mem[key] = zh
            if today and _day_count["date"] == today:
                _day_count["n"] += 1
    return zh


def clean_zh(text):
    """去掉机翻常见残留：多余空格、英文标点。"""
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    t = t.replace(",", "，").replace(";", "；") if t.count(",") > 2 else t
    return t


def needs_translate(ev, cfg):
    """是否需要翻译：英文源 + 开关打开 + 还没有中文标题。"""
    if not (cfg.get("translate") or {}).get("enabled", True):
        return False
    if not cfg.get("ai", {}).get("translate_en", True):
        return False
    return ev.get("lang") == "en" and not ev.get("title_zh")


def fill_title(ev, cfg, today=""):
    """给事件补中文标题。优先用 AI 已生成的结果，其次机翻。"""
    if ev.get("title_zh"):
        return ev["title_zh"]
    if not needs_translate(ev, cfg):
        return ""
    zh = to_zh(ev.get("title", ""), cfg, today=today)
    if zh:
        ev["title_zh"] = clean_zh(zh)
        return ev["title_zh"]
    return ""


def display_title(ev):
    """页面与推送统一取标题：有中文用中文，否则原文。"""
    return ev.get("title_zh") or ev.get("title") or ""


def _lead_sentences(text, limit=380):
    """截取正文开头若干整句，避免机翻把句子切成两半。"""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    # 回退到最后一个句末标点
    pos = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if pos > limit * 0.5:
        return cut[:pos + 1]
    return cut


def body_summary(ev, cfg, today=""):
    """无 AI 时把英文正文机翻成中文摘要。只对推送事件调用，控制额度消耗。"""
    if ev.get("lang") != "en":
        return ""
    src = ev.get("body") or ""
    if len(src.strip()) < 20:
        return ""
    lead = _lead_sentences(src)
    return clean_zh(to_zh(lead, cfg, today=today))
