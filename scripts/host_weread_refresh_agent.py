#!/usr/bin/env python3
"""宿主机微信读书 Cookie 刷新代理（常驻，由 launchd 启动）。

为什么需要它
------------
- 微信读书的登录态 profile 由 macOS 钥匙串加密，容器内 Linux Chromium **解密不了**，
  因此浏览器刷新动作必须在宿主机用本机 Chrome 完成。
- 但用户希望「点击执行 / 定时任务」时，若 Cookie 过期就**自动刷新**再同步文章，
  而不是手动跑到宿主机敲命令。
- 解法：宿主机常驻一个轻量 HTTP 代理。容器在同步前调用其 ``/refresh`` 端点，
  代理用本机 Chrome 做无头刷新（登录态失效时再弹窗扫码），结果写回数据卷
  ``wx.lic``；容器随后读到最新 Cookie 去同步文章。

刷新策略（verify-first，尽量不启动浏览器）
----------------------------------------
1. 先验证当前 wx.lic 里的 Cookie 是否仍能拉到数据；有效则直接返回（秒级，不启动浏览器）。
2. 无效则做**无头刷新**（复用持久化 profile，通常秒级~数十秒）。
3. 无头仍失败（登录态过期）→ 后台开一个可见 Chrome 窗口让用户扫码，HTTP 立即返回
   ``needs_scan``，扫码完成后 Cookie 自动写回，用户重新点一次执行即可。

容器侧通过环境变量 ``WEREAD_REFRESH_AGENT_URL``（默认
``http://host.docker.internal:9876/refresh``）找到本代理。

注意：本文件运行在**宿主机**（macOS），使用宿主机 Python venv + Playwright + 本机 Chrome，
不是容器内的 Linux Chromium。
"""
import os
import sys
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 日志实时落盘（launchd 场景 stdout 重定向为文件时避免全缓冲滞后）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# 让脚本能 import 项目的 core 包
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 指向宿主机上容器挂载的数据卷 wx.lic / profile（与容器 /app/data 同一物理目录）
os.environ.setdefault("WEREAD_LIC_PATH", "/Users/yangqing/wechat-rss-data/wx.lic")
os.environ.setdefault(
    "WEREAD_PROFILE_DIR",
    "/Users/yangqing/wechat-rss-data/weread-chrome-profile",
)

from core.weread_cookie_refresh import (  # noqa: E402
    refresh_weread_cookie,
    _verify_cookie,
    _load_weread_data,
)

HOST = os.environ.get("WEREAD_AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("WEREAD_AGENT_PORT", "9876"))

# 串行化刷新，避免并发（如 07:55 定时 + 手动执行同时触发）争抢同一 profile
_refresh_lock = threading.Lock()


def do_refresh() -> dict:
    """执行一次「确保 Cookie 新鲜」的逻辑。

    返回: ``{"ok": bool, "refreshed": bool, "needs_scan": bool, "message": str}``
    """
    # 1) 当前 Cookie 仍有效 → 无需启动浏览器，直接返回
    _, data = _load_weread_data()
    cookie = (data.get("cookie") or "").strip()
    if cookie and _verify_cookie(cookie):
        return {
            "ok": True,
            "refreshed": False,
            "needs_scan": False,
            "message": "Cookie 仍有效，无需刷新",
        }

    # 2) 需要刷新：无头优先（cooldown_hours=0 强制真刷新，绕过 6h 冷却误判）
    try:
        ok = refresh_weread_cookie(verbose=True, headless_only=True, cooldown_hours=0)
    except Exception as e:
        ok = False
        print(f"[agent] 无头刷新异常: {e}")

    if ok:
        return {
            "ok": True,
            "refreshed": True,
            "needs_scan": False,
            "message": "Cookie 已自动刷新",
        }

    # 3) 无头失败：登录态可能已过期，后台开可见窗口让用户扫码（不阻塞 HTTP 请求）
    def _bg_scan():
        try:
            # 不带 headless_only → 无头失败会弹窗等待扫码（最长 5 分钟）
            refresh_weread_cookie(verbose=True, cooldown_hours=0)
        except Exception as e:
            print(f"[agent] 后台扫码刷新异常: {e}")

    threading.Thread(target=_bg_scan, daemon=True).start()
    return {
        "ok": False,
        "refreshed": False,
        "needs_scan": True,
        "message": "Cookie 已过期，请在弹出的浏览器窗口中扫码登录微信读书",
    }


def do_renew() -> dict:
    """强制无头续期（供容器侧每 2 小时的自动续期任务调用）。

    与 do_refresh 的区别：cookie 有效时也执行无头刷新（用 seed 打开 reader 页，
    抓最新 cookie 写回），实现「失效前主动续期」；cookie 无效时 headless_only=True
    静默失败、绝不弹窗（登录仍走用户手动扫码）。
    """
    try:
        ok = refresh_weread_cookie(verbose=True, headless_only=True, cooldown_hours=0)
    except Exception as e:
        ok = False
        print(f"[agent] 续期异常: {e}")
    return {
        "ok": ok,
        "renewed": ok,
        "message": "Cookie 已续期" if ok else "Cookie 无效或续期失败（等待手动登录，未弹窗）",
    }


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _refresh(self):
        with _refresh_lock:
            result = do_refresh()
        self._send(200, result)

    def _renew(self):
        with _refresh_lock:
            result = do_renew()
        self._send(200, result)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/health", ""):
            self._send(200, {"ok": True, "message": "agent alive"})
        elif path == "/browsers":
            # 宿主机 OS 上探测已安装浏览器（供容器 /weread/browsers 代理给前端下拉）
            from core.browser_detect import detect_browsers
            self._send(200, {"browsers": detect_browsers()})
        elif path == "/renew":
            self._renew()
        elif path == "/refresh":
            self._refresh()
        else:
            self._send(404, {"ok": False, "message": "not found"})

    def do_POST(self):
        # /refresh 与 /renew 同时支持 POST（容器 urllib 默认 POST）
        path = self.path.split("?")[0].rstrip("/")
        if path == "/renew":
            self._renew()
        else:
            self._refresh()

    def log_message(self, *args):
        # 避免把每个请求打到 stderr（已在 do_refresh 内打印关键日志）
        pass


def main():
    os.makedirs(os.path.dirname(os.environ.get("WEREAD_LIC_PATH", "")) or ".", exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    print(f"[agent] 微信读书 Cookie 刷新代理已启动: http://{HOST}:{PORT}/refresh")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[agent] 代理已停止")


if __name__ == "__main__":
    main()
