"""内置网页服务：看板 + 设置 + 数据接口。

安全边界：只按白名单放行——
  页面（index/setup）、PWA 资源、data/*.json、assets/*
config.yaml / settings.json / 源码目录一律 404，
避免同一 WiFi 下别人把推送地址和配置读走。
"""
import json
import mimetypes
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import config as cfg_mod
from . import notify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 页面被人打开过的最后时间。启动器靠它确认“浏览器真的把页面打开了”，
# 而不是只看进程有没有起来——很多情况下进程起来了、屏幕上一片空白。
_last_page_hit = 0.0
_hit_lock = threading.Lock()

_PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/setup": "setup.html",
    "/setup.html": "setup.html",
}
_ASSETS = {"/manifest.webmanifest", "/sw.js"}


class Handler(BaseHTTPRequestHandler):
    server_version = "Radar/1.0"

    def log_message(self, fmt, *args):      # 静默，避免刷屏
        pass

    # ---------------- GET ----------------
    def do_GET(self):
        path = urlparse(self.path).path

        if path in _PAGES:
            touch_page()
            return self._file(ROOT / _PAGES[path], "text/html; charset=utf-8", nocache=True)
        if path in _ASSETS:
            ctype = ("application/manifest+json" if path.endswith("manifest.webmanifest")
                     else "application/javascript; charset=utf-8")
            return self._file(ROOT / path.lstrip("/"), ctype, nocache=True)
        if path.startswith("/assets/"):
            f = (ROOT / path.lstrip("/")).resolve()
            if ROOT.resolve() in f.parents and f.is_file():
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self._file(f, ctype, nocache=False)
            return self._json({"error": "not found"}, 404)
        if path.startswith("/data/") and path.endswith(".json"):
            f = (DATA / Path(path).name)
            if f.is_file():
                return self._file(f, "application/json; charset=utf-8", nocache=True)
            return self._json({"error": "not found"}, 404)
        if path == "/api/ping":
            return self._ping()
        if path == "/api/settings":
            return self._get_settings()

        return self._json({"error": "not found"}, 404)

    # ---------------- POST ----------------
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            return self._json({"error": "请求格式错误"}, 400)

        if path == "/api/settings":
            return self._save_settings(body)
        if path == "/api/test":
            return self._test_push()
        return self._json({"error": "not found"}, 404)

    # ---------------- 实现 ----------------
    def _ping(self):
        n = 0
        f = DATA / "events.json"
        if f.is_file():
            try:
                n = len(json.loads(f.read_text(encoding="utf-8")))
            except ValueError:
                n = 0
        self._json({"ok": True, "events": n})

    def _get_settings(self):
        s = cfg_mod.read_settings()
        url = s.get("bark_url") or ""
        self._json({"bark_configured": bool(url),
                    "bark_url_masked": cfg_mod.mask_url(url),
                    "browser": s.get("browser") or "auto"})

    def _save_settings(self, body):
        patch = {}
        if "bark_url" in body:
            url = (body.get("bark_url") or "").strip()
            if url and not url.startswith(("http://", "https://")):
                return self._json({"error": "推送地址应以 http(s):// 开头"}, 400)
            patch["bark_url"] = url or None
        if "browser" in body:
            b = (body.get("browser") or "auto").strip().lower()
            if b not in cfg_mod.BROWSER_CHOICES:
                return self._json({"error": "不认识的浏览器选项"}, 400)
            patch["browser"] = b
        if not patch:
            return self._json({"error": "没有要保存的内容"}, 400)

        cfg_mod.save_settings(patch)
        s = cfg_mod.read_settings()
        self._json({"ok": True,
                    "bark_url_masked": cfg_mod.mask_url(s.get("bark_url") or ""),
                    "browser": s.get("browser") or "auto"})

    def _test_push(self):
        cfg = cfg_mod.load_config()
        ok, msg = notify.bark(
            cfg.get("notify"),
            "🔴 测试推送",
            "收到这条，说明手机通知已经通了。\n真实告警会带来源和时间。",
            "", "L2")
        self._json({"ok": bool(ok), "message": "已发送，看看手机" if ok else str(msg)})

    # ---------------- 输出 ----------------
    def _file(self, path, ctype, nocache=False):
        try:
            data = Path(path).read_bytes()
        except OSError:
            return self._json({"error": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if nocache:
            self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def touch_page():
    global _last_page_hit
    with _hit_lock:
        _last_page_hit = time.time()


def page_status():
    with _hit_lock:
        return _last_page_hit


def wait_page_hit(since, timeout=6.0):
    """等“页面被打开”这件事真的发生。since 传启动浏览器之前的时间戳。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page_status() >= since:
            return True
        time.sleep(0.2)
    return False


def lan_ip():
    """取本机在局域网里的地址，用于手机访问。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def find_running(port=8000, tries=12, timeout=0.35):
    """端口链上是不是已经有一份本程序在跑？是就返回它的端口号。

    作用：防止双击两次起两个实例、两个进程同时写 data/ 和发推送。
    """
    import urllib.request
    for i in range(tries):
        p = port + i
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/api/ping",
                                        timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("ok") is True and "events" in data:
                return p
        except Exception:
            continue
    return None


def serve(port=8000, tries=12):
    """启动服务，返回 (httpd, 实际端口)。端口被占则自动顺延。"""
    last = None
    for i in range(tries):
        p = port + i
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", p), Handler)
            httpd.daemon_threads = True
            t = threading.Thread(target=httpd.serve_forever, daemon=True,
                                 name="radar-web")
            t.start()
            return httpd, p
        except OSError as exc:
            last = exc
            continue
    raise OSError(f"8000-{port + tries - 1} 端口都被占用：{last}")
