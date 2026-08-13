"""微信读书 Cookie 刷新（全部在宿主机执行，容器只消费结果）。

架构：微信读书登录态 profile 由 macOS 钥匙串加密，容器内 Linux Chromium 解密不了，
因此**所有浏览器操作（首次扫码 + 每日自动刷新）都在宿主机用本机 Chrome 完成**，
刷新成功后把明文 Cookie 写回数据卷的 wx.lic；容器（jobs/mps.add_job）只读取 wx.lic
的 Cookie 同步文章，不在容器内启动浏览器。

调用方：scripts/refresh_weread_cookie.py（GUI 扫码 / --headless 每日自动，由 launchd 触发）。

流程：
1. 用本机 Chrome（Playwright 驱动）打开配置的公众号主页 URL（reader 页，形如
   https://weread.qq.com/web/mp/reader/xxxx，**不要配成带 bookId 的 /web/mp/articles
   接口地址**——接口地址会被重定向且不是给人看的页面）；
2. 主页内部会发出 /web/mp/articles 请求，从该请求头提取最新 Cookie（回退
   context.cookies 拼接）；
3. 写回 wx.lic 的 weread_data，并记录 cookie_refresh_last_ts（冷却用）；
4. 若 headless_only=False 且取不到有效 Cookie，弹可见窗口提示扫码登录，等待后更新。

注意：
- 直接读写 wx.lic（WEREAD_LIC_PATH 指定，默认 ./data/wx.lic）。
- 持久化 profile 目录由 WEREAD_PROFILE_DIR 指定，默认 ~/.cache/we-mp-rss/weread-chrome-profile；
  应与容器挂载的数据卷指向同一物理目录（如 /Users/yangqing/wechat-rss-data/weread-chrome-profile），
  由本机 Chrome 持有登录态，宿主刷新时复用。
- 宿主机调用一般不传 force_bundled（使用 wx.lic 中配置的 browser_path 指向的本机 Chrome）。
"""
import os
import sys
import json
import time
import subprocess

import yaml

DEFAULT_LIC_PATH = os.environ.get("WEREAD_LIC_PATH", "./data/wx.lic")
DEFAULT_PROFILE_DIR = os.environ.get(
    "WEREAD_PROFILE_DIR",
    os.path.expanduser("~/.cache/we-mp-rss/weread-chrome-profile"),
)


def _read_lic(lic_path: str = DEFAULT_LIC_PATH) -> dict:
    """直接读取 wx.lic（YAML），避免引入 core.config 的重依赖链。"""
    if not os.path.exists(lic_path):
        return {}
    with open(lic_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_lic(lic_path: str, doc: dict):
    with open(lic_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)


def _load_weread_data(lic_path: str = DEFAULT_LIC_PATH):
    """返回 (doc, data)，doc 为整个 YAML 文档，data 为 weread_data 字典。"""
    doc = _read_lic(lic_path)
    data = doc.get("weread_data", {})
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    return doc, data


def _save_cookie(cookie: str, name: str = "", lic_path: str = DEFAULT_LIC_PATH):
    """把最新 cookie 写回 wx.lic 的 weread_data（保留文档其他部分）。

    同时同步 vid 字段：配置页与 /weread 状态接口用 weread_data.vid 判断是否已配置，
    若只更新 cookie 而不更新 vid，换账号扫码后会残留上一个账号的 vid。
    """
    doc, data = _load_weread_data(lic_path)
    data["cookie"] = cookie
    vid = extract_vid(cookie)
    if vid:
        data["vid"] = vid
    if name:
        data["name"] = name
    data["cookie_refresh_last_ts"] = time.time()
    doc["weread_data"] = data
    _write_lic(lic_path, doc)


def extract_vid(cookie: str) -> str:
    """从 Cookie 字符串中提取 wr_vid。"""
    for item in (cookie or "").split(";"):
        item = item.strip()
        if item.startswith("wr_vid="):
            return item[len("wr_vid="):].strip()
    return ""


def _dedupe_cookie(cookie: str) -> str:
    """去掉重复键（浏览器注入种子后再回抓可能产生重复 wr_vid/wr_skey 等），保留首次出现。

    重复键会导致服务端取到第一个（可能是过期）值，故保存与注入前都需去重。
    """
    kept = {}
    for item in (cookie or "").split(";"):
        item = item.strip()
        if "=" in item:
            k, _, v = item.partition("=")
            k = k.strip()
            if k and k not in kept:
                kept[k] = f"{k}={v.strip()}"
    return "; ".join(kept.values())


def _verify_cookie(cookie: str) -> bool:
    """实打实请求一次 weread MP 接口，确认 Cookie 真能拉到数据。

    仅检查 'wr_vid=' 不够：过期 Cookie 同样带 wr_vid，服务端会以 -2012/-2041 等拒绝。
    故刷新后必须用真实接口验证，避免把过期 Cookie 误判为有效（假阳性）。
    判定标准：响应 JSON 含非零 errCode（如 -2012 登录超时、-2041 等）即视为无效。
    无 requests 时退化为 True（不阻断），但宿主机场景应装有 requests。
    """
    try:
        import requests
    except ImportError:
        return True
    try:
        r = requests.get(
            "https://weread.qq.com/web/mp/articles",
            params={"bookId": "MP_WXS_3528995129", "offset": 0},
            headers={
                "Cookie": cookie,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://weread.qq.com/",
            },
            timeout=30,
        )
        try:
            j = r.json()
        except Exception:
            return False
        if isinstance(j, dict):
            code = j.get("errCode", j.get("errcode", 0))
            if code:  # 任何非零 errCode 均表示无效（含 -2012/-2041 等）
                return False
            # 有实际数据字段才视为有效
            if "reviews" in j or "articles" in j or "synckey" in j or j.get("bookId"):
                return True
        return False
    except Exception:
        return False


def _launch_browser(p, headless, profile_dir, browser_path, force_bundled=False):
    '''启动 Playwright 持久化上下文（仅在「读取/续期 Cookie」时使用，不用于登录）。'''
    args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    if force_bundled or not browser_path:
        return p.chromium.launch_persistent_context(profile_dir, headless=headless, args=args)
    return p.chromium.launch_persistent_context(
        profile_dir, headless=headless, executable_path=browser_path, args=args)


def _find_browser(browser_path):
    '''定位本机 Chrome 二进制：优先用 wx.lic 的 browser_path，缺失则按平台兜底探测。
    返回路径或空串（空串表示需要引导用户安装）。'''
    if browser_path and os.path.exists(browser_path):
        return browser_path
    candidates = []
    if sys.platform == 'darwin':
        candidates = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    elif sys.platform.startswith('linux'):
        candidates = [
            '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium', '/usr/bin/chromium-browser',
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ''


def _open_normal_browser(profile_dir, browser_path, url, verbose=True):
    '''打开一个「真实」浏览器窗口（不由 Playwright 驱动），避免被微信读书识别为自动化。

    - 优先用本机 Chrome 二进制 + --user-data-dir 绑定专用 profile（登录态可被后续无头读取）；
    - 若 Chrome 二进制缺失，则退回系统 open / xdg-open / start（使用默认 profile）。
    返回 True 表示已发起打开动作。'''
    chrome = _find_browser(browser_path)
    if not chrome:
        # macOS 的 open 是系统内置命令，无需安装；真正会「缺失」的是 Chrome 本身。
        if sys.platform == 'darwin':
            tip = '未找到 Chrome，请先安装：brew install --cask google-chrome  或前往 https://www.google.com/chrome/ 下载'
        elif sys.platform.startswith('linux'):
            tip = '未找到 Chrome/Chromium，请先安装：sudo apt install -y google-chrome-stable  或 chromium'
        else:
            tip = '未找到 Chrome，请先安装 Google Chrome'
        if verbose:
            print('[refresh] ' + tip)
        if sys.platform == 'darwin':
            subprocess.Popen(['open', url])
        elif sys.platform.startswith('linux'):
            subprocess.Popen(['xdg-open', url])
        elif sys.platform == 'win32':
            os.startfile(url)
        return True

    if sys.platform == 'darwin':
        subprocess.Popen([chrome, '--user-data-dir=' + profile_dir,
                          '--no-first-run', '--no-default-browser-check', url])
    elif sys.platform.startswith('linux'):
        subprocess.Popen([chrome, '--user-data-dir=' + profile_dir, '--no-first-run', url])
    elif sys.platform == 'win32':
        subprocess.Popen([chrome, '--user-data-dir=' + profile_dir, '--no-first-run', url])
    else:
        subprocess.Popen([chrome, '--user-data-dir=' + profile_dir, url])
    return True


def _profile_locked(profile_dir):
    '''Chrome 是否正占用该 profile（SingletonLock 存在表示有进程持有）。'''
    return os.path.exists(os.path.join(profile_dir, 'SingletonLock'))


def _wait_login_via_normal_browser(profile_dir, browser_path, url, timeout_s=600, verbose=True):
    '''session 过期时：打开真实浏览器请用户扫码登录；用户关闭窗口释放锁后，
    用无头方式从同一 profile 读取 Cookie 并验证。

    关键点：登录发生在「真实 Chrome」（navigator.webdriver=false、无自动化 CDP 连接），
    不会被微信读书风控；登录态持久化进 profile_dir，关闭后可由 Playwright 无头读取，
    全程只在「读取」阶段用到 Playwright，不会触发图形验证/操作太频繁。'''
    from playwright.sync_api import sync_playwright

    # 等待上一步无头刷新残留的 Chrome 完全退出（避免 SingletonLock 冲突
    # 导致真实浏览器一启动就被 abort，日志里反复出现的 profile in use 就是它）
    lock_wait_until = time.time() + 30
    while _profile_locked(profile_dir) and time.time() < lock_wait_until:
        time.sleep(2)

    # 打开首页而非 reader 页：登录态过期时 reader 页不保证展示二维码，首页必有扫码入口
    if not _open_normal_browser(profile_dir, browser_path, 'https://weread.qq.com/', verbose=verbose):
        return ''
    if verbose:
        print('[refresh] 请在弹出的 Chrome 窗口用微信扫码登录；登录成功后请关闭该窗口（最多等待 '
              + str(timeout_s // 60) + ' 分钟）')
    deadline = time.time() + timeout_s
    last_err = ''
    while time.time() < deadline:
        if not _profile_locked(profile_dir):
            try:
                with sync_playwright() as p:
                    context = _launch_browser(
                        p, headless=True, profile_dir=profile_dir, browser_path=browser_path)
                    cookies = context.cookies('https://weread.qq.com')
                    ck = _dedupe_cookie('; '.join(c['name'] + '=' + c['value'] for c in cookies))
                    context.close()
                if 'wr_vid=' in ck and _verify_cookie(ck):
                    return ck
                last_err = 'profile 中尚未读到有效微信读书 Cookie（可能还没登录完）'
            except Exception as e:  # noqa: BLE001
                last_err = '读取 profile Cookie 失败（浏览器可能仍开着）: ' + str(e)
        time.sleep(5)
    if verbose and last_err:
        print('[refresh] ' + last_err)
    return ''


def _extract_cookie_from_page(page, context, url: str) -> str:
    """优先从 /web/mp/articles 请求头取 Cookie，回退 context.cookies 拼接。"""
    captured = {}

    def _on_request(request):
        if "web/mp/articles" in request.url:
            captured["cookie"] = request.headers.get("cookie", "")

    page.on("request", _on_request)
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
    except Exception as e:
        print(f"[refresh] 打开页面异常: {e}")
    # 优先使用 network 请求头中的 Cookie
    cookie = captured.get("cookie", "").strip()
    if cookie:
        return cookie
    # 回退：直接用 context 的 cookie jar 拼接
    try:
        cookies = context.cookies("https://weread.qq.com")
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    except Exception:
        return ""


def refresh_weread_cookie(verbose: bool = True, headless_only: bool = False,
                          force_bundled: bool = False, cooldown_hours: float = 6.0) -> bool:
    """执行一次 Cookie 自动刷新。成功更新（或确认仍新鲜）返回 True，否则 False。

    headless_only: True 时只做无头刷新，不在登录失效时弹窗扫码（容器内使用）。
    force_bundled: True 时忽略 browser_path，使用 Playwright 自带 Chromium
                   （容器内没有宿主机 Chrome 路径，且需与数据卷共享 profile）。
    cooldown_hours: 距离上次成功刷新不足该时长且已有 Cookie 时，视为仍有效，跳过刷新。
    """
    lic, data = _load_weread_data()
    url = (data.get("cookie_refresh_url") or "").strip()
    browser_path = (data.get("browser_path") or "").strip()
    browser_type = (data.get("browser_type") or "chrome").strip() or "chrome"

    if not url:
        if verbose:
            print("[refresh] 未配置 cookie_refresh_url，跳过自动刷新（请在微信读书配置页填写）")
        return False

    # 冷却：上次刷新成功且在冷却期内，且已有 Cookie，则视为仍有效，跳过
    if cooldown_hours and cooldown_hours > 0:
        last_ts = data.get("cookie_refresh_last_ts") or 0
        has_cookie = bool((data.get("cookie") or "").strip())
        if has_cookie and last_ts and (time.time() - float(last_ts)) < cooldown_hours * 3600:
            # 冷却期内：只有经真实接口验证 Cookie 仍有效才跳过刷新；
            # 否则（已过期 / 旧时间戳是假阳性）必须强制刷新，不能被旧时间戳卡住。
            if _verify_cookie((data.get("cookie") or "").strip()):
                if verbose:
                    print(f"[refresh] Cookie 在冷却期内（{cooldown_hours:g}h）且仍有效，跳过刷新")
                return True
            if verbose:
                print("[refresh] Cookie 在冷却期内但已失效，强制刷新")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if verbose:
            print("[refresh] 未安装 playwright，请执行: pip install playwright && playwright install chromium")
        return False

    profile_dir = DEFAULT_PROFILE_DIR
    os.makedirs(profile_dir, exist_ok=True)

    # 浏览器启动逻辑已抽为模块级 _launch_browser（见上方），此处不再内联定义

    def _try(headless: bool, wait_login: bool = False, timeout_s: int = 300,
             force_bundled: bool = False, seed_cookie: str = "") -> str:
        """打开页面并提取 Cookie；wait_login=True 时若未登录，保持窗口等待用户扫码。

        seed_cookie: wx.lic 中已有的 Cookie，作为登录态种子注入上下文。
        解决宿主(macOS Chrome)/容器(Linux Chromium) profile cookie 加密不互通的问题：
        容器无头刷新无法解密宿主写入的 profile cookie，故改以 wx.lic 的 Cookie 为可信源。
        """
        with sync_playwright() as p:
            context = _launch_browser(
                p, headless=headless, profile_dir=profile_dir,
                browser_path=browser_path, force_bundled=force_bundled,
            )
            page = context.new_page()
            # 扫码模式下绝不注入种子 Cookie：过期 Cookie 会让页面停在“已登录但失效”的
            # 状态，既出不来二维码，也会让下面的等待逻辑误判为“已拿到 Cookie”而直接退出。
            if wait_login:
                seed_cookie = ""
                try:
                    context.clear_cookies()
                except Exception:
                    pass
            # 注入种子 Cookie（来源：wx.lic，先去重避免重复键）。即便 profile 跨平台
            # 无法复用也能复用登录态；若种子本身已过期，则必须扫码重建有效 session。
            seed_cookie = _dedupe_cookie(seed_cookie)
            if seed_cookie:
                try:
                    cookies = []
                    for item in seed_cookie.split(";"):
                        item = item.strip()
                        if "=" in item:
                            name, _, value = item.partition("=")
                            name = name.strip()
                            value = value.strip()
                            if name and value:
                                cookies.append({
                                    "name": name,
                                    "value": value,
                                    "url": "https://weread.qq.com",
                                })
                    if cookies:
                        context.add_cookies(cookies)
                        if verbose:
                            print(f"[refresh] 已注入 wx.lic 种子 Cookie（{len(cookies)} 项）")
                except Exception as e:
                    if verbose:
                        print(f"[refresh] 注入种子 Cookie 失败（不影响）: {e}")
            try:
                cookie = _extract_cookie_from_page(page, context, url)
                cookie = _dedupe_cookie(cookie)
                if wait_login:
                    # 扫码模式：只有“验证真实有效”的 Cookie 才算数；否则保持可见窗口，
                    # 轮询等待用户扫码登录（登录态持久化到 profile_dir）。
                    if cookie and _verify_cookie(cookie):
                        return cookie
                    # 确保窗口停在可扫码的登录入口（reader 页未登录时可能是报错页）
                    try:
                        page.goto("https://weread.qq.com/", wait_until="domcontentloaded",
                                  timeout=30000)
                    except Exception:
                        pass
                    if verbose:
                        print("[refresh] 请在弹出的 Chrome 窗口中用微信扫码登录微信读书…")
                    deadline = time.time() + timeout_s
                    while time.time() < deadline:
                        try:
                            cookies = context.cookies("https://weread.qq.com")
                            ck = _dedupe_cookie(
                                "; ".join(f"{c['name']}={c['value']}" for c in cookies))
                        except Exception:
                            ck = ""
                        if "wr_vid=" in ck and _verify_cookie(ck):
                            cookie = ck
                            break
                        time.sleep(3)
                    else:
                        cookie = ""
                return cookie
            finally:
                context.close()

    # 1) 常规无头刷新：登录态持久化，通常直接拿到有效 Cookie
    #    注入 wx.lic 已有 Cookie 作为种子（跨平台 profile 不互通时的可信回退）
    seed_cookie = (data.get("cookie") or "").strip()
    cookie = _try(headless=True, force_bundled=force_bundled, seed_cookie=seed_cookie)
    # 必须实打实验证 Cookie 真能拉到数据，避免把过期 Cookie 误判为有效（假阳性）
    if cookie and "wr_vid=" in cookie and _verify_cookie(cookie):
        vid = extract_vid(cookie)
        _save_cookie(cookie, name=data.get("name", ""))
        if verbose:
            print(f"[refresh] Cookie 已自动更新 (vid={vid})")
        return True

    # 2) 未拿到有效 Cookie（或拿到但验证失败＝过期）
    if headless_only:
        if verbose:
            print("[refresh] Cookie 无效/已过期（接口返回 -2012）。无头模式不弹窗，"
                  "请在本机运行 'python scripts/refresh_weread_cookie.py' 扫码登录后刷新")
        return False

    # 3) 登录态已过期：打开「真实」浏览器（非 Playwright 驱动）请用户手动登录，
    #    避免被微信读书风控识别为自动化。登录态持久化进 profile_dir，关闭窗口后
    #    由无头方式从同一 profile 读取 Cookie 写回。
    if verbose:
        print('[refresh] 登录态已过期，将打开本机真实 Chrome 请你扫码登录（非自动化窗口，不会触发风控）…')
    cookie = _wait_login_via_normal_browser(
        profile_dir, browser_path, url, timeout_s=600, verbose=verbose)
    if cookie and 'wr_vid=' in cookie and _verify_cookie(cookie):
        vid = extract_vid(cookie)
        _save_cookie(cookie, name=data.get('name', ''))
        if verbose:
            print('[refresh] 扫码登录后 Cookie 已更新 (vid=' + vid + ')')
        return True

    if verbose:
        print('[refresh] 等待登录超时或 Cookie 仍无效，请检查微信读书登录状态')
    return False


def request_host_refresh(timeout_s: int = 180) -> dict:
    """容器内调用宿主机刷新代理（**不在容器内启动浏览器**）。

    浏览器刷新动作由宿主机代理完成（macOS 钥匙串加密的 profile 容器内解不开）。
    容器内只负责：在同步文章前，发现/怀疑 Cookie 过期时，请宿主机代理去刷新，
    代理把最新明文 Cookie 写回数据卷 wx.lic，容器随后读取它同步文章。

    可通过环境变量 ``WEREAD_REFRESH_AGENT_URL`` 配置代理地址
    （默认 http://host.docker.internal:9876/refresh）。

    返回: ``{"triggered": bool, "ok": bool, "needs_scan": bool, "message": str}``
      - triggered=False 表示未配置代理（手动模式，跳过自动刷新，不报错）；
      - ok=False 且 needs_scan=True 表示登录态过期需扫码，调用方应中止任务并提示用户；
      - ok=False 且 needs_scan=False 表示代理调用本身失败（网络/代理未启动等）。
    """
    import urllib.request

    agent_url = (os.environ.get("WEREAD_REFRESH_AGENT_URL") or "").strip()
    if not agent_url:
        # 未配置代理：保持向后兼容，不强制刷新（手动模式）
        return {
            "triggered": False,
            "ok": True,
            "needs_scan": False,
            "message": "未配置 WEREAD_REFRESH_AGENT_URL，跳过自动刷新（手动模式）",
        }
    if not agent_url.endswith("/refresh"):
        agent_url = agent_url.rstrip("/") + "/refresh"
    try:
        req = urllib.request.Request(
            agent_url,
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return {
            "triggered": True,
            "ok": bool(payload.get("ok")),
            "needs_scan": bool(payload.get("needs_scan")),
            "message": payload.get("message", ""),
        }
    except Exception as e:
        return {
            "triggered": True,
            "ok": False,
            "needs_scan": False,
            "message": f"调用宿主机刷新代理失败: {e}",
        }


if __name__ == "__main__":
    import sys

    ok = refresh_weread_cookie(verbose=True)
    sys.exit(0 if ok else 1)
