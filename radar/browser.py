"""打开看板页面：直接点名启动浏览器，不走系统默认关联那条模糊路径。

为什么不再只用 webbrowser.open：
  Windows 上它最终是 os.startfile(url) → ShellExecute + 默认程序关联。
  一旦默认程序被“浏览器保护”（360 安全卫士、火绒之类）改过或拦下，
  它会静默失败——要么返回 False，要么返回成功但屏幕上什么都没有。
  机器上装了四个浏览器时最容易出这种事，因为默认关联随时会被人改。

所以这里的顺序是：
  1. 从注册表读出“默认浏览器到底是哪个 exe”
  2. 用 subprocess 直接点名启动它，带上 --new-window，窗口一定弹到最前
  3. 上面任一步不成，就按 Edge → Chrome → Firefox → 360 → QQ 硬试一遍
  4. 全都不成，才退回 os.startfile / webbrowser
  5. 无论成没成，都把结果和人话报回来，不再“没动静也不知道为什么”
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

LABELS = {
    "edge": "Microsoft Edge",
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "360": "360 浏览器",
    "qq": "QQ 浏览器",
}

ORDER = ("edge", "chrome", "firefox", "360", "qq")
ALLOWED = {"auto", "default"} | set(ORDER)

# 常见安装位置（{VAR} 由环境变量展开）
_PATHS = {
    "edge": (
        r"{ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        r"{ProgramFiles}\Microsoft\Edge\Application\msedge.exe",
    ),
    "chrome": (
        r"{ProgramFiles}\Google\Chrome\Application\chrome.exe",
        r"{ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        r"{LOCALAPPDATA}\Google\Chrome\Application\chrome.exe",
    ),
    "firefox": (
        r"{ProgramFiles}\Mozilla Firefox\firefox.exe",
        r"{ProgramFiles(x86)}\Mozilla Firefox\firefox.exe",
    ),
    "360": (
        r"{ProgramFiles(x86)}\360\360se6\Application\360se.exe",
        r"{ProgramFiles}\360\360se6\Application\360se.exe",
        r"{ProgramFiles(x86)}\360Chrome\Chrome\Application\360chrome.exe",
        r"{LOCALAPPDATA}\360Chrome\Chrome\Application\360chrome.exe",
        r"{LOCALAPPDATA}\360ChromeX\Chrome\Application\360ChromeX.exe",
        r"{ProgramFiles(x86)}\360ChromeX\Chrome\Application\360ChromeX.exe",
    ),
    "qq": (
        r"{ProgramFiles(x86)}\Tencent\QQBrowser\QQBrowser.exe",
        r"{ProgramFiles}\Tencent\QQBrowser\QQBrowser.exe",
        r"{LOCALAPPDATA}\Tencent\QQBrowser\Application\QQBrowser.exe",
    ),
}

# 注册表 App Paths 里可能出现的关键名（同一个浏览器不同版本叫法不同）
_APP_PATHS = {
    "edge": ("msedge.exe",),
    "chrome": ("chrome.exe",),
    "firefox": ("firefox.exe",),
    "360": ("360se6.exe", "360se.exe", "360chrome.exe"),
    "qq": ("QQBrowser.exe",),
}

_FAMILY = {
    "msedge.exe": "edge",
    "chrome.exe": "chrome",
    "firefox.exe": "firefox",
    "360se.exe": "360",
    "360chrome.exe": "360",
    "360chromex.exe": "360",
    "qqbrowser.exe": "qq",
}

_URL_ASSOC = (r"SOFTWARE\Microsoft\Windows\Shell\Associations"
              r"\UrlAssociations\http\UserChoice")


# ---------------------------------------------------------------- 注册表读取
def _reg(path, name=""):
    """先用户、后机器，读不到返回 None。非 Windows 直接 None。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, path) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            continue
    return None


def _reg_class(path, name=""):
    """HKCR 下的读取。ProgId 只挂在 HKCR / HK{LM,CU}\\SOFTWARE\\Classes，不在根上。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for root, prefix in ((winreg.HKEY_CLASSES_ROOT, ""),
                         (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Classes\\"),
                         (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\\")):
        try:
            with winreg.OpenKey(root, prefix + path) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            continue
    return None


def _exe_from_cmd(cmd):
    """从 'C:\\...\\chrome.exe" --single-argument %1' 里抠出 exe 路径。"""
    if not cmd:
        return None
    cmd = cmd.strip()
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        if end > 0:
            return cmd[1:end]
    cut = len(cmd)
    low = cmd.lower()
    for sep in (" -", " /", " %"):
        i = low.find(sep)
        if 0 < i < cut:
            cut = i
    return cmd[:cut].strip().strip('"')


def default_exe():
    """返回 (exe路径|None, ProgId|None)。"""
    progid = _reg(_URL_ASSOC, "ProgId")
    if not progid:
        return None, None
    exe = _exe_from_cmd(_reg_class(progid + r"\shell\open\command"))
    if exe and os.path.isfile(exe):
        return exe, progid
    return None, progid


# ---------------------------------------------------------------- 安装位置
def _expand(p):
    def repl(m):
        return os.environ.get(m.group(1), "\x00")
    return re.sub(r"\{([^}]+)\}", repl, p)


def _from_app_paths(name):
    for exe_name in _APP_PATHS.get(name, ()):
        val = _reg(r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\"
                   + exe_name)
        if val:
            val = val.strip().strip('"')
            if os.path.isfile(val):
                return val
    return None


def _from_known(name):
    for raw in _PATHS.get(name, ()):
        p = _expand(raw)
        if "\x00" not in p and os.path.isfile(p):
            return p
    return None


def detect():
    """{名字: exe 路径}，只含真的装了的。"""
    found = {}
    for name in ORDER:
        exe = _from_app_paths(name) or _from_known(name)
        if exe:
            found[name] = exe
    return found


def family(exe):
    if not exe:
        return None
    return _FAMILY.get(os.path.basename(exe).lower())


# ---------------------------------------------------------------- 启动
def _argv(exe, url):
    if family(exe) == "firefox":
        return [exe, "-new-window", url]
    return [exe, "--new-window", url]


def _spawn(exe, url):
    try:
        subprocess.Popen(_argv(exe, url),
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         close_fds=True)
        return True
    except (OSError, ValueError):
        return False


def _system_default(url):
    """老办法：交给系统关联。只在点名全失败时才用。"""
    if sys.platform == "win32" and hasattr(os, "startfile"):
        try:
            os.startfile(url)       # noqa: S606  桌面工具，就该这么开
            return True
        except OSError:
            pass
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:
        return False


# ---------------------------------------------------------------- 等端口
def _wait_port(url, timeout=8.0):
    """服务刚起时立刻打开会撞上“无法访问”，先确认端口通了。"""
    u = urlparse(url)
    host = u.hostname or "127.0.0.1"
    port = u.port or 80
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.6):
                return True
        except OSError:
            time.sleep(0.15)
    return False


# ---------------------------------------------------------------- 对外
def open_url(url, prefer="auto", wait=8.0, verify=None, max_try=3):
    """打开 url。返回 (是否成功, 用的浏览器名, 说明)。

    prefer: auto / default / edge / chrome / firefox / 360 / qq
    verify: 可选回调 verify(时间戳) -> bool。传 server.wait_page_hit 就变成
            “页面真的被打开了才算成功”，这是唯一可信的判断方式——
            进程起来了、屏幕却一片空白的情况太常见了。
    """
    if not _wait_port(url, wait):
        return False, "", "网页服务还没起来"

    prefer = (prefer or "auto").lower()
    if prefer not in ALLOWED:
        prefer = "auto"
    have = detect()

    # 候选：(名字, exe, 备注)
    cands = []
    if prefer == "default":
        cands.append(("", None, "系统关联"))
    elif prefer in have:
        cands.append((prefer, have[prefer], "指定"))
    elif prefer in LABELS:
        return False, LABELS[prefer], "这台机器上没找到它，可能是绿色版装在别处"

    if prefer == "auto":
        exe, _progid = default_exe()
        if exe:
            fam = family(exe) or ""
            cands.append((fam, exe, "系统默认浏览器"))
        for name, exe in have.items():
            cands.append((name, exe, "已安装"))
        cands.append(("", None, "系统关联"))

    seen = set()
    tried = []
    for name, exe, note in cands:
        key = exe or "__default__"
        if key in seen:
            continue
        seen.add(key)
        if len(tried) >= max_try:
            break

        started = time.time()
        ok = _system_default(url) if exe is None else _spawn(exe, url)
        if ok and verify is not None:
            ok = bool(verify(started))
        label = LABELS.get(name) or os.path.basename(exe or "") or "系统默认浏览器"
        tried.append(label)
        if ok:
            return True, label, note

    if not tried:
        return False, "", "没有可用的浏览器"
    return False, "", "试过 " + "、".join(tried) + "，页面都没打开"
