"""浏览器安装路径探测（在宿主机 OS 上运行）。

用途：微信读书配置页需要选择「用哪个本机浏览器打开 weread.qq.com 提取 Cookie」。
后端容器是 Linux，看不到宿主的浏览器；本模块由宿主机刷新代理
（scripts/host_weread_refresh_agent.py 的 GET /browsers）在宿主 OS 上调用，
把「浏览器 → 可执行文件路径」探测出来，供前端下拉选择。

设计：
- BROWSERS 为注册表式，新增浏览器只需加一行（app 名 / bundle_id / Windows 路径）。
- macOS：定位 .app 目录（已知路径 + ~/Applications + mdfind 按 bundle_id 兜底），
  再读 Contents/Info.plist 的 CFBundleExecutable 拼出真实二进制路径，
  避免硬编码每个浏览器的可执行文件名。
- Windows：优先注册表 App Paths（HKCU/HKLM），再按常见安装路径兜底。
- supported=False 表示刷新链路（core/weread_cookie_refresh.py）尚未适配该内核
  （Firefox 需要 p.firefox + -profile，暂未支持），前端据此禁用/提示。
- 仅依赖标准库，无第三方依赖。
"""

import os
import sys

BROWSERS = [
    {
        "key": "chrome",
        "name": "Google Chrome",
        "type": "chromium",
        "supported": True,
        "darwin_app": "Google Chrome.app",
        "darwin_bundle_id": "com.google.Chrome",
        "windows_reg": "chrome.exe",
        "windows_paths": [
            "{ProgramFiles}\\Google\\Chrome\\Application\\chrome.exe",
            "{ProgramFilesX86}\\Google\\Chrome\\Application\\chrome.exe",
            "{LocalAppData}\\Google\\Chrome\\Application\\chrome.exe",
        ],
    },
    {
        "key": "msedge",
        "name": "Microsoft Edge",
        "type": "chromium",
        "supported": True,
        "darwin_app": "Microsoft Edge.app",
        "darwin_bundle_id": "com.microsoft.edgemac",
        "windows_reg": "msedge.exe",
        "windows_paths": [
            "{ProgramFilesX86}\\Microsoft\\Edge\\Application\\msedge.exe",
            "{ProgramFiles}\\Microsoft\\Edge\\Application\\msedge.exe",
        ],
    },
    {
        "key": "firefox",
        "name": "Firefox",
        "type": "firefox",
        "supported": False,  # 刷新链路暂未适配（需 p.firefox + -profile）
        "darwin_app": "Firefox.app",
        "darwin_bundle_id": "org.mozilla.firefox",
        "windows_reg": "firefox.exe",
        "windows_paths": [
            "{ProgramFiles}\\Mozilla Firefox\\firefox.exe",
            "{ProgramFilesX86}\\Mozilla Firefox\\firefox.exe",
        ],
    },
    {
        "key": "opera",
        "name": "Opera",
        "type": "chromium",
        "supported": True,
        "darwin_app": "Opera.app",
        "darwin_bundle_id": "com.operasoftware.Opera",
        "windows_reg": "opera.exe",
        "windows_paths": [
            "{LocalAppData}\\Programs\\Opera\\opera.exe",
            "{ProgramFiles}\\Opera\\opera.exe",
        ],
    },
    {
        "key": "brave",
        "name": "Brave",
        "type": "chromium",
        "supported": True,
        "darwin_app": "Brave Browser.app",
        "darwin_bundle_id": "com.brave.Browser",
        "windows_reg": "brave.exe",
        "windows_paths": [
            "{ProgramFiles}\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
            "{LocalAppData}\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
        ],
    },
    {
        "key": "vivaldi",
        "name": "Vivaldi",
        "type": "chromium",
        "supported": True,
        "darwin_app": "Vivaldi.app",
        "darwin_bundle_id": "com.vivaldi.Vivaldi",
        "windows_reg": "vivaldi.exe",
        "windows_paths": [
            "{LocalAppData}\\Vivaldi\\Application\\vivaldi.exe",
            "{ProgramFiles}\\Vivaldi\\Application\\vivaldi.exe",
        ],
    },
    {
        "key": "arc",
        "name": "Arc",
        "type": "chromium",
        "supported": True,
        "darwin_app": "Arc.app",
        "darwin_bundle_id": "company.thebrowser.Browser",
        "windows_reg": "Arc.exe",
        "windows_paths": [
            "{LocalAppData}\\Programs\\Arc\\Arc.exe",
            "{LocalAppData}\\Arc\\Arc.exe",
        ],
    },
    {
        "key": "tabbit",
        "name": "Tabbit Browser",
        "type": "chromium",
        "supported": True,
        "darwin_app": "Tabbit.app",
        "darwin_bundle_id": "com.tabbit-ai.Tabbit",
        "windows_reg": "Tabbit Browser.exe",
        "windows_paths": [
            "{LocalAppData}\\Tabbit Browser\\Application\\Tabbit Browser.exe",
            "{ProgramFiles}\\Tabbit Browser\\Application\\Tabbit Browser.exe",
        ],
    },
]


def _macos_find_app(app_name: str, bundle_id: str = "") -> str:
    """定位 macOS 上的 .app 目录；找不到返回空串。"""
    candidates = [
        os.path.join("/Applications", app_name),
        os.path.join(os.path.expanduser("~/Applications"), app_name),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    # mdfind 按 bundle id 兜底（覆盖非默认安装位置）
    if bundle_id:
        try:
            import subprocess
            out = subprocess.run(
                ["mdfind", "kMDItemCFBundleIdentifier == '%s'" % bundle_id],
                capture_output=True, text=True, timeout=10,
            )
            for line in (out.stdout or "").splitlines():
                line = line.strip()
                if line.endswith(".app") and os.path.isdir(line):
                    return line
        except Exception:
            pass
    return ""


def _macos_executable(app_path: str) -> str:
    """从 .app 目录解析真实可执行文件路径（读 Info.plist CFBundleExecutable）。"""
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    if os.path.exists(plist_path):
        try:
            import plistlib
            with open(plist_path, "rb") as f:
                info = plistlib.load(f)
            exe = info.get("CFBundleExecutable")
            if exe:
                p = os.path.join(app_path, "Contents", "MacOS", exe)
                if os.path.isfile(p):
                    return p
        except Exception:
            pass
    # 兜底：Contents/MacOS 下第一个可执行文件
    macos_dir = os.path.join(app_path, "Contents", "MacOS")
    if os.path.isdir(macos_dir):
        for name in sorted(os.listdir(macos_dir)):
            p = os.path.join(macos_dir, name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return ""


def _win_expand(path: str) -> str:
    """展开 {ProgramFiles} / {ProgramFilesX86} / {LocalAppData} 占位符。"""
    env = os.environ
    return (path
            .replace("{ProgramFilesX86}", env.get("ProgramFiles(x86)", ""))
            .replace("{ProgramFiles}", env.get("ProgramFiles", ""))
            .replace("{LocalAppData}", env.get("LOCALAPPDATA", "")))


def _win_reg_app_path(value_name: str) -> str:
    """Windows 注册表 App Paths 探测（HKCU 优先，HKLM 兜底）。"""
    try:
        import winreg
    except ImportError:
        return ""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
    try:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(hive, key_path)
                sub = winreg.OpenKey(key, value_name)
                try:
                    val, _ = winreg.QueryValueEx(sub, "")
                    if val and os.path.isfile(val):
                        return val
                finally:
                    winreg.CloseKey(sub)
                    winreg.CloseKey(key)
            except OSError:
                continue
    except Exception:
        pass
    return ""


def _detect_one(browser: dict) -> str:
    """按当前 OS 探测单个浏览器的可执行文件路径；未安装返回空串。"""
    if sys.platform == "darwin":
        app = _macos_find_app(browser["darwin_app"], browser.get("darwin_bundle_id", ""))
        if app:
            return _macos_executable(app)
        return ""
    if sys.platform == "win32":
        path = _win_reg_app_path(browser.get("windows_reg", ""))
        if path:
            return path
        for p in browser.get("windows_paths", []):
            expanded = _win_expand(p)
            if expanded and os.path.isfile(expanded):
                return expanded
        return ""
    # Linux 等其他平台：宿主代理只在 macOS/Windows 上运行，返回空
    return ""


def detect_browsers() -> list:
    """探测全部注册浏览器，返回 [{key, name, type, supported, path}]。"""
    result = []
    for b in BROWSERS:
        result.append({
            "key": b["key"],
            "name": b["name"],
            "type": b["type"],
            "supported": b["supported"],
            "path": _detect_one(b),
        })
    return result


def detect_browser(key: str) -> dict:
    """按 key 探测单个浏览器，未注册返回 None。"""
    for b in BROWSERS:
        if b["key"] == key:
            return {
                "key": b["key"],
                "name": b["name"],
                "type": b["type"],
                "supported": b["supported"],
                "path": _detect_one(b),
            }
    return None


if __name__ == "__main__":
    for item in detect_browsers():
        print("%-22s supported=%-5s path=%s" % (
            item["name"], item["supported"], item["path"] or "(未安装)"))
