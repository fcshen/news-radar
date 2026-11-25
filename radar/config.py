"""配置读取：config.yaml 为主，settings.json 与 BARK_URL 环境变量覆盖。

分层原因：
- config.yaml 带大量注释，给人和版本管理看，不能被程序回写覆盖（会丢注释）
- settings.json 是运行时设置（网页上填的推送地址等），程序可写
- 环境变量给云端 Secrets 用，优先级最高
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "settings.json"

# 网页上“用哪个浏览器打开看板”的可选值
BROWSER_CHOICES = {"auto", "default", "edge", "chrome", "firefox", "360", "qq"}


def load_config(path=None):
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    _apply_settings(cfg)
    _apply_env(cfg)
    return cfg


def read_settings():
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_settings(patch):
    cur = read_settings()
    for k, v in patch.items():
        if v is None:
            cur.pop(k, None)
        else:
            cur[k] = v
    SETTINGS.write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return cur


def _apply_settings(cfg):
    s = read_settings()
    url = s.get("bark_url")
    if url:
        bark = cfg.setdefault("notify", {}).setdefault("bark", {})
        bark["url"] = url
        bark["enabled"] = True
    if s.get("bark_group"):
        cfg.setdefault("notify", {}).setdefault("bark", {})["group"] = s["bark_group"]


def _apply_env(cfg):
    url = os.environ.get("BARK_URL")
    if url:
        bark = cfg.setdefault("notify", {}).setdefault("bark", {})
        bark["url"] = url
        bark["enabled"] = True


def mask_url(url):
    """只回显域名和尾号，避免整条推送地址泄露在网页源码里。"""
    if not url:
        return ""
    try:
        p = urlparse(url)
    except ValueError:
        return "…"
    host = f"{p.scheme}://{p.netloc}" if p.netloc else ""
    tail = (p.path or "").rstrip("/")[-6:]
    return f"{host}/…{tail}" if tail else f"{host}/…"
