#!/usr/bin/env python3
"""金融事件雷达 · 启动器

一个进程同时做三件事：
  1. 在局域网起网页（电脑和手机都能打开）
  2. 打开浏览器
  3. 开始采集与推送

用法：
  双击 启动.bat             日常使用
  python app.py              命令行等价写法
  python app.py --no-browser 不自动开浏览器
  python app.py --port 8080  指定端口
  python app.py --browsers   看看这台机器上认出了哪几个浏览器
  python app.py --browser 360 点名用某个浏览器打开（edge/chrome/firefox/360/qq）
"""
import argparse
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from radar import browser as web             # noqa: E402
from radar import config as cfg_mod          # noqa: E402
from radar import server                     # noqa: E402
import main as engine                        # noqa: E402

# 启动日志：窗口一闪而过时，靠这个回看刚才到底走到哪一步、报了什么错
LOG = ROOT / "data" / "_launch.log"


def log_line(msg):
    try:
        LOG.parent.mkdir(exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 300_000:
            LOG.write_text("", encoding="utf-8")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except OSError:
        pass


def print_qr(url):
    try:
        import qrcode
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    try:
        qr.print_ascii(invert=True)
    except Exception:
        pass


def banner(port, cfg):
    ip = server.lan_ip()
    local = f"http://127.0.0.1:{port}/"
    lan = f"http://{ip}:{port}/"
    bark = ((cfg.get("notify") or {}).get("bark") or {})
    bark_on = bool(bark.get("enabled") and bark.get("url"))

    print()
    print("  ┌────────────────────────────────────────────┐")
    print("  │            金融事件雷达  已启动            │")
    print("  └────────────────────────────────────────────┘")
    print()
    print(f"  电脑打开：  {local}")
    print(f"  手机打开：  {lan}")
    print(f"             （手机要和电脑连同一个 WiFi）")
    print()
    if bark_on:
        print("  手机推送：  已配置 ✓")
    else:
        print(f"  手机推送：  未配置 → 打开 {local}setup 填一次即可")
    print()
    print("  ──────────────────────────────────────────────")
    print("  手机安装成 App（推荐做一次）：")
    print("    iPhone：Safari 打开上面的手机地址 → 分享 → 添加到主屏幕")
    print("    安卓  ：浏览器打开 → 菜单 → 添加到主屏幕 / 安装应用")
    print("  ──────────────────────────────────────────────")
    print()
    return lan


def open_board(port, pref="auto"):
    """把看板页面打开，并且把结果说清楚——不成功也别让人对着空屏猜。

    判断标准是“服务端真的收到了页面请求”，不是“进程有没有起来”。
    """
    url = f"http://127.0.0.1:{port}/"
    ok, name, note = web.open_url(url, pref, verify=server.wait_page_hit)
    log_line(f"浏览器 {'成功' if ok else '失败'} {name} {note} prefer={pref}")
    if ok:
        tail = f"（{note}）" if note else ""
        print(f"  浏览器：    已用 {name} 打开 {tail}")
    else:
        print(f"  浏览器：    没能自动打开（{note}）")
        print(f"              请手动把下面这行复制到浏览器：{url}")
    print()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--browser", default=None,
                    help="auto/default/edge/chrome/firefox/360/qq")
    ap.add_argument("--browsers", action="store_true", help="列出识别到的浏览器后退出")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--minutes", type=int, default=0)
    ap.add_argument("--once", action="store_true", help="只跑一轮，调试用")
    args = ap.parse_args()

    if args.browsers:
        found = web.detect()
        dflt, progid = web.default_exe()
        print()
        print("  识别到的浏览器：")
        if found:
            for name, exe in found.items():
                print(f"    {web.LABELS[name]:<16} {exe}")
        else:
            print("    一个都没找到（绿色版装在别处的话，用 --browser 手动指定）")
        print()
        if dflt:
            print(f"  系统默认浏览器：{os.path.basename(dflt)}  ({dflt})")
        else:
            print(f"  系统默认浏览器：读不出来（ProgId={progid}）")
        print()
        return 0

    cfg = cfg_mod.load_config()
    (ROOT / "data").mkdir(exist_ok=True)
    pref = args.browser or cfg_mod.read_settings().get("browser") or "auto"
    log_line(f"启动 argv={sys.argv[1:]} python={sys.executable}")

    # 已经有一份在跑：别起第二个（会两个进程抢同一份数据、重复推送）
    if not (args.once or args.dry_run or args.browsers):
        running = server.find_running(args.port)
        if running:
            print()
            print(f"  已经在运行了（端口 {running}），不再重复启动。")
            if args.no_browser:
                print(f"  看板地址：http://127.0.0.1:{running}/")
            else:
                open_board(running, pref)
            print("  这个窗口可以关掉了。")
            print()
            return 0

    try:
        _httpd, port = server.serve(args.port)
    except OSError as exc:
        print(f"启动失败：{exc}")
        return 1

    lan = banner(port, cfg)
    log_line(f"服务已起 port={port} 手机地址={lan}")

    if not args.no_browser:
        open_board(port, pref)

    print_qr(lan)

    print("  采集已开始，首轮约 30 秒。关闭本窗口即停止。")
    print("  " + "─" * 44)
    print()

    try:
        return engine.run(minutes=args.minutes, dry_run=args.dry_run, once=args.once)
    except KeyboardInterrupt:
        print("\n已手动停止。")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        log_line("崩溃\n" + traceback.format_exc())
        traceback.print_exc()
        sys.exit(1)
