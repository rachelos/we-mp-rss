"""
跨平台解析本地 Chromium 内核浏览器（Chrome / Edge / Chromium）可执行文件路径。

设计目标：
- 不写死任何机器专属绝对路径（如某台 Windows 的 D:\\Tools\\...）。
- 跨平台：Win11 / Docker-Linux / macOS 均可用。
- 默认“不启用”：解析不到时返回 None，由调用方回退到 Playwright 自带浏览器，
  从而保持上游默认行为（默认 webkit）完全不变，Docker/Linux 零回归。

解析优先级：
  1. 环境变量 CHROME_EXECUTABLE_PATH（跨平台、最高优先级，用户显式指定）
  2. 当前操作系统的“标准安装位置”自动发现（仅当文件确实存在时才采用）
  3. 都没有 -> 返回 None
"""
import os
import sys

# 仅收录各平台“标准”安装位置；不含任何机器专属路径。
# 找不到时列表自然跳过，返回 None（调用方回退自带浏览器）。
_CANDIDATES = {
    "win32": [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ],
    "linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ],
}


def get_chrome_executable_path() -> "str | None":
    """返回可用的 Chromium 内核浏览器可执行文件路径；无则返回 None。

    返回 None 时，调用方应保持原有浏览器类型（如上游默认的 webkit），
    由 Playwright 启动其自带浏览器，确保 Docker/Linux 默认行为不变。
    """
    env = os.environ.get("CHROME_EXECUTABLE_PATH")
    if env and os.path.exists(env):
        return env
    for cand in _CANDIDATES.get(sys.platform, []):
        if cand and os.path.exists(cand):
            return cand
    return None
