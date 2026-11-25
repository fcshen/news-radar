"""AI 摘要：三层降级，任何一层挂掉都不影响主流程。"""
import json
import os
import re

import requests

SYSTEM = (
    "你是金融信息编辑，服务对象是 A 股、ETF、期货交易者。"
    "你只做两件事：提炼事实、判断可能影响。不预测价格，不给买卖建议。"
    "事实与推断必须分开，推断要克制。"
)

PROMPT = """消息来源：{source}
原文语言：{lang}
标题：{title}
正文：{body}

请输出严格 JSON，不要任何多余文字：
{{"title_zh": "{title_hint}",
  "summary": "40-70字的事实摘要，中文，只陈述原文有的事实，不加形容词",
  "impact": "20-30字，这条消息对 A 股/ETF/期货 的可能影响，属于推断，语气克制"}}
title_zh 要求：原文是英文时译成中文标题，25 字以内，保留公司名、机构名等专有名词的原样（可中英并列）；原文已是中文时原样返回。
summary 必须是中文，原文是英文也要译成中文，不要出现英文长句。
如果这条与 A 股、ETF、期货完全无关，summary 填 "无关"，impact 填空字符串。"""


def _call_openai_compat(base_url, api_key, model, prompt, max_tokens, timeout):
    r = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _parse(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return (
            str(data.get("title_zh", "")).strip(),
            str(data.get("summary", "")).strip(),
            str(data.get("impact", "")).strip(),
        )
    except json.JSONDecodeError:
        return None


def summarize(ev, cfg):
    """返回 (title_zh, summary, impact, engine)。engine 记录实际使用的层级。

    英文消息的中文标题在同一次调用里产出，不额外计费。
    """
    ai = cfg.get("ai", {})
    if not ai.get("enabled", True):
        return "", _fallback(ev), "", "off"

    is_en = ev.get("lang") == "en"
    prompt = PROMPT.format(
        source=f"{ev['source']}（{ev.get('tier', '')}）",
        lang="英文" if is_en else "中文",
        title=ev["title"][:300],
        body=ev["body"][:1200],
        title_hint="" if is_en else ev["title"][:60],
    )
    max_tokens = ai.get("max_tokens", 220)
    timeout = ai.get("timeout", 20)

    for layer in ("primary", "fallback"):
        conf = ai.get(layer) or {}
        key = os.environ.get(
            "ZHIPU_API_KEY" if conf.get("provider") == "zhipu" else "SILICONFLOW_API_KEY",
            conf.get("api_key", ""),
        )
        if not key:
            continue
        try:
            raw = _call_openai_compat(conf["base_url"], key, conf["model"],
                                      prompt, max_tokens, timeout)
            parsed = _parse(raw)
            if parsed:
                title_zh, summary, impact = parsed
                if summary == "无关":
                    return title_zh, "", "", layer
                return title_zh, summary, impact, layer
        except Exception:
            continue

    # 走到这里说明 AI 不可用。英文消息不返回英文原文（那等于没翻），
    # 由调用方交给机翻层处理；中文消息用正文截断兜底。
    if ev.get("lang") == "en":
        return "", "", "", "template"
    return "", _fallback(ev), "", "template"


def _fallback(ev):
    body = ev.get("body") or ev["title"]
    body = body.replace("\n", " ")
    return body[:90] + ("…" if len(body) > 90 else "")
