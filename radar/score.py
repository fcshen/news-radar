"""打分：权威度 + 相关性 + 主体×谓词组合 + 烈度 + 扩散 + 时段

相比"数关键词"，这一版多了两个判断力来源：
1. 主体词库 —— 华为 / 希音 / 软银 出现在标题里，本身就是事件
2. 事件类型词库 —— 裁定 / 罚款 / 制裁 / 内幕消息，与主语无关，属于实质动作

真正的分水岭是 **主体 × 谓词 同时命中**：那是"谁出了什么事"。
只有主体没有谓词（宁德时代入股某公司），只有谓词没有主体（某公司被罚款），
都不该和"华为被判有罪"同分。
"""
import re
from datetime import datetime

from . import lexicon as lx

TIER_SCORE = {
    "official": 100,
    "exchange": 96,
    "authority": 80,
    "media": 55,
    "unverified": 20,
}

TIER_LABEL = {
    "official": "官方",
    "exchange": "交易所",
    "authority": "权威媒体",
    "media": "媒体",
    "unverified": "未证实",
}

# 涨跌幅 ≥ 此值视为"有事的行情"，而不是普通波动
PCT_STRONG = 3.0


def _hits(text, words):
    return lx.hits(text, words)


def _pct_bonus(texts):
    """标题里出现涨跌幅百分比。≥5% 加 8，≥3% 加 4。"""
    best = 0.0
    for t in texts:
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", t):
            try:
                best = max(best, float(m.group(1)))
            except ValueError:
                pass
    if best >= 8:
        return 12
    if best >= 5:
        return 8
    if best >= PCT_STRONG:
        return 4
    return 0


def _combo(ent_n, pred_n):
    """主体 × 谓词的组合分。这是整张打分表的重点。"""
    if pred_n and ent_n:
        return 15 + 6 * min(ent_n, 2) + 5 * min(pred_n, 3)
    if pred_n:
        return 8 + 4 * min(pred_n, 3)
    if ent_n:
        return 4 + 2 * min(ent_n, 2)
    return 0


def evaluate(ev, cfg, source_count=1):
    """返回 (score, level, reason)。"""
    kw = cfg.get("keywords", {})
    th = cfg.get("thresholds", {})
    title = ev["title"]
    text = f"{title} {ev.get('body', '')}"
    text_low = text.lower()
    title_low = title.lower()
    tier = TIER_SCORE.get(ev.get("tier", "media"), 55)
    channel = ev.get("channel", "")
    is_en = ev.get("lang") == "en"

    # ---------- 行情异动：直接升级 ----------
    if channel == "quote":
        return 74.0, "L2", "行情触发"

    # ---------- 主体 × 谓词 ----------
    # 主体只在标题里数（正文提到不算，"某公司回应华为"不算华为的事）
    ent_list = lx.entities(title, title_low)
    ent_n = len(ent_list)
    pred_n = _hits(title, lx.EVENT_TYPE) + _hits(title_low, lx.EVENT_TYPE_EN)
    combo = _combo(ent_n, pred_n)

    # 司法定罪比一般"调查"重一档：判了，就是既成事实
    conviction = (_hits(title, lx.CONVICTION)
                  + _hits(title_low, lx.CONVICTION_EN))
    if conviction:
        combo += 8

    # 观点/访谈：是解释，不是事实，只进摘要不推即时
    is_opinion = (_hits(title, lx.OPINION) > 0
                  or _hits(title_low, lx.OPINION_EN) > 0)

    # ---------- 相关性：用户配置的行业词 + 主体 ----------
    if is_en:
        core = _hits(text_low, kw.get("en_core") or lx.EN_CORE)
        sector = _hits(text_low, kw.get("en_sector") or lx.EN_SECTOR)
        relevance = min(40, core * 15 + sector * 5 + min(ent_n, 2) * 7)
        severity = 0
        excluded = _hits(text_low, lx.EN_EXCLUDE) > 0 and combo == 0
    else:
        core = _hits(text, kw.get("core", []))
        sector = _hits(text, kw.get("sector", []))
        relevance = min(40, core * 15 + sector * 8 + min(ent_n, 2) * 6)
        severity = min(15, _hits(title, lx.SEVERITY) * 8)
        excluded = any(w in text for w in kw.get("exclude", []))

    if excluded and combo == 0 and core == 0:
        return 0.0, "L0", "与市场无关"

    # ---------- 交易所公告：走实质词规则 ----------
    is_notice = channel in ("szse", "sse", "cninfo")
    substantive = _hits(title, lx.SUBSTANTIVE)
    routine_hit = _hits(title, lx.ROUTINE) > 0

    spread = min(10, max(0, source_count - 1) * 2)
    burst = _burst_bonus(ev)
    pct = _pct_bonus([title])

    total = tier * 0.35 + relevance + severity + combo + spread + burst + pct

    if is_notice:
        if substantive == 0:
            total = min(total, 25)          # 无实质内容，沉底
    elif routine_hit and combo == 0:
        total *= 0.45

    # 观点类封顶：券商怎么看不是事件，最多进摘要
    if is_opinion and conviction == 0:
        total = min(total * 0.85, 62)

    total = round(min(100.0, total), 1)

    push = th.get("push", 68)
    digest = th.get("digest", 50)

    # L3 = 叫醒级。只有官方/交易所源，或命中极端事件词，才配
    extreme = (_hits(title, lx.EXTREME) > 0
               or _hits(title_low, lx.EXTREME_EN) > 0)
    if extreme and total >= 80:
        level = "L3"
    elif tier >= 96 and total >= 88:
        level = "L3"
    elif total >= push:
        level = "L2"
    elif total >= digest:
        level = "L1"
    else:
        level = "L0"

    if is_opinion and conviction == 0 and level in ("L2", "L3"):
        level = "L1"

    # 交易所实质公告保底进摘要，命中烈度词升即时
    if is_notice and substantive and level == "L0":
        level = "L1"
        total = max(total, 52)

    reason = (f"tier={tier:.0f} ent={ent_n}{ent_list[:2]} pred={pred_n} "
              f"conv={conviction} combo={combo} rel={relevance} sev={severity} "
              f"pct={pct} op={'Y' if is_opinion else 'N'} "
              f"spread={spread} burst={burst}")
    return total, level, reason


def _burst_bonus(ev):
    try:
        dt = datetime.fromisoformat(ev["ts"])
    except (ValueError, KeyError):
        return 0
    t = dt.hour * 60 + dt.minute
    if 555 <= t <= 900:
        return 5
    if t >= 1260 or t <= 150:
        return 5
    if 420 <= t <= 555:
        return 4
    if 1020 <= t <= 1200:
        return 3
    return 1


def apply_score(ev, cfg, source_count=1):
    score, level, reason = evaluate(ev, cfg, source_count)
    ev["score"] = score
    ev["level"] = level
    ev["reason"] = reason
    return ev
