"""
Async Playwright Controller - 完全异步版本
彻底解决 asyncio 兼容性问题
"""
import os
import sys
import json
import asyncio
import time
from urllib.parse import urlparse, unquote
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Windows 需要使用 ProactorEventLoop 以支持 Playwright 子进程
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from core.print import print_error, print_info, print_warning
from driver.anti_crawler_config import AntiCrawlerConfig
from driver.chrome_path import get_chrome_executable_path

@dataclass
class Metrics:
    """性能指标数据类"""
    browser_startup_time: float = 0.0
    page_creation_time: float = 0.0
    memory_usage_mb: float = 0.0
    open_pages: int = 0
    open_contexts: int = 0
    total_operations: int = 0
    failed_operations: int = 0
    avg_operation_time: float = 0.0
    cleanup_count: int = 0
    cleanup_failures: int = 0
    avg_cleanup_time: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    last_updated_at: datetime = field(default_factory=datetime.now)


class PlaywrightController:
    """
    异步 Playwright 控制器

    完全基于 async/await,与 FastAPI 完美兼容

    Features:
        - 集成反爬虫配置（user_agent、viewport、extra_http_headers等）
        - 自动注入JavaScript反检测脚本
        - 支持移动端/桌面端模式切换
    """

    def __init__(self, headless: bool = None,
                 browser_type: str = "webkit",
                 proxy_url: Optional[str] = "",
                 user_agent: Optional[str] = None,
                 debug: bool = False,
                 mobile_mode: bool = False,
                 apply_anti_crawler: bool = True):
        """
        初始化异步控制器

        Args:
            headless: 是否无头模式（默认从环境变量HEADLESS读取，默认True）
            browser_type: 浏览器类型
            proxy_url: 代理URL
            user_agent: 用户代理（可选，优先使用用户指定值）
            debug: 调试模式
            mobile_mode: 是否为移动端模式
        """
        # 默认使用 headless=True（适合Docker环境），可通过环境变量覆盖
        self.headless = os.environ.get("HEADLESS", "true").lower() == "true" if headless is None else headless
        self.browser_type = browser_type
        self.proxy_url = proxy_url
        self.debug = debug
        self.mobile_mode = mobile_mode
        # 是否应用反爬虫注入（extra_http_headers + 反检测脚本）。
        # 反爬头含 Cache-Control / Sec-Fetch-* 等非 CORS 安全头，会触发跨域预检，
        # 导致部分站点（如微信公众平台登录页）自身 JS 资源加载失败、二维码无法渲染。
        # 微信登录等场景需退化为普通浏览器，故提供关闭开关。
        self.apply_anti_crawler = apply_anti_crawler

        # 反爬虫配置实例
        self.anti_crawler_config = AntiCrawlerConfig()

        # User-Agent处理：
        # - 如果用户指定了user_agent，优先使用用户指定的
        # - 否则从AntiCrawlerConfig获取
        if user_agent:
            self.user_agent = user_agent
        else:
            self.user_agent = self.anti_crawler_config._ua_generator.get_realistic_user_agent(mobile_mode)

        # Playwright 对象
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        # 性能指标
        self.metrics = Metrics()
        
    async def start_browser(self) -> None:
        """
        启动浏览器(异步) - 集成反爬虫配置
        """
        if self._browser is not None:
            return

        start_time = time.time()

        try:
            # Windows 上检查事件循环类型
            if sys.platform == 'win32':
                try:
                    loop = asyncio.get_running_loop()
                    loop_type = type(loop).__name__
                    if self.debug:
                        print_info(f"当前事件循环类型: {loop_type}")
                except RuntimeError:
                    pass

            # 导入 async_playwright
            from playwright.async_api import async_playwright

            # 启动 Playwright
            self._playwright = await async_playwright().start()

            # ===== 本地 Chrome 支持（可选，避免强制 playwright install 下载浏览器）=====
            # 仅当通过环境变量 CHROME_EXECUTABLE_PATH 显式指定（或自动发现到本机标准安装的
            # Chromium 内核浏览器）时才启用；否则保持上游默认浏览器（默认 webkit，由 Playwright 自带），
            # 跨平台可移植，Docker/Linux 默认行为不受影响。
            CHROME_PATH = get_chrome_executable_path()
            if CHROME_PATH:
                self.browser_type = "chromium"
                print_info(f"使用本地 Chrome: {CHROME_PATH}（跳过 Playwright 浏览器下载）")

            # 选择浏览器类型
            browser_launcher = getattr(self._playwright, self.browser_type)

            # 启动浏览器
            # 注意：不同浏览器支持的参数不同
            # - Chromium: 支持 --disable-blink-features, --disable-dev-shm-usage
            # - Firefox: 不支持这些参数
            # - WebKit: 不支持这些参数
            launch_options = {
                "headless": self.headless,
            }

            # 只为 Chromium 添加特定参数
            if self.browser_type == "chromium":
                launch_options["args"] = [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ]
                # 使用本地 Chrome 可执行文件，避免下载 Playwright 浏览器
                if CHROME_PATH:
                    launch_options["executable_path"] = CHROME_PATH

            # 添加代理
            if self.proxy_url:
                launch_options["proxy"] = {"server": self.proxy_url}

            self._browser = await browser_launcher.launch(**launch_options)

            # ========== 核心改造：使用AntiCrawlerConfig ==========
            # 获取反爬虫配置
            anti_config = self.anti_crawler_config.get_anti_crawler_config(self.mobile_mode)

            # 构建上下文配置
            context_options = {
                "user_agent": self.user_agent,  # 使用初始化时确定的UA
                "viewport": anti_config.get("viewport", {"width": 1920, "height": 1080}),
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
            }

            # 应用额外的HTTP头（反爬注入可能破坏跨域资源加载，关闭时跳过）
            if self.apply_anti_crawler and "extra_http_headers" in anti_config:
                context_options["extra_http_headers"] = anti_config["extra_http_headers"]

            # 应用其他可选配置
            for key in ["java_script_enabled", "ignore_https_errors", "bypass_csp"]:
                if key in anti_config:
                    context_options[key] = anti_config[key]

            self._context = await self._browser.new_context(**context_options)

            # 创建页面
            self._page = await self._context.new_page()

            # ========== 核心改造：注入反检测脚本（关闭反爬时跳过）==========
            if self.apply_anti_crawler:
                await self._apply_anti_crawler_scripts(self._page)

            # 记录启动时间
            self.metrics.browser_startup_time = time.time() - start_time

            if self.debug:
                print_info(f"浏览器启动成功,耗时: {self.metrics.browser_startup_time:.2f}s")
                print_info(f"反爬虫配置已应用: mobile_mode={self.mobile_mode}")

        except Exception as e:
            print_error(f"启动浏览器失败: {str(e)}")
            raise

    async def _apply_anti_crawler_scripts(self, page) -> None:
        """
        应用反爬虫脚本到页面

        Args:
            page: Playwright页面对象
        """
        try:
            # 获取初始化脚本
            init_script = AntiCrawlerConfig.get_init_script()

            # 注入初始化脚本（在页面加载前执行）
            await page.add_init_script(init_script)

            if self.debug:
                print_info("反检测脚本注入成功")

        except Exception as e:
            # 注入失败不中断流程，仅记录警告
            print_warning(f"反检测脚本注入失败: {str(e)}")
            
    async def open_url(self, url: str,
                       wait_until: str = "domcontentloaded",
                       timeout: int = 30000) -> bool:
        """
        打开URL(异步)

        Args:
            url: 目标URL
            wait_until: 等待策略
            timeout: 超时时间(毫秒)

        Returns:
            是否成功
        """
        # 检查 Page 对象是否有效，如果无效则重新启动浏览器
        if not self.is_page_valid():
            if self.debug:
                print_warning("Page 对象无效，重新启动浏览器...")
            await self.start_browser()

        start_time = time.time()

        try:
            # 导航到URL
            await self._page.goto(url, wait_until=wait_until, timeout=timeout)

            # 智能等待
            await self._smart_wait()

            # 记录指标
            load_time = time.time() - start_time
            self.metrics.total_operations += 1
            self.metrics.avg_operation_time = (
                (self.metrics.avg_operation_time * (self.metrics.total_operations - 1) + load_time)
                / self.metrics.total_operations
            )

            if self.debug:
                print_info(f"页面加载成功: {url}, 耗时: {load_time:.2f}s")

            return True

        except Exception as e:
            self.metrics.failed_operations += 1
            print_error(f"打开URL失败: {url}, 错误: {str(e)}")
            # 如果打开URL失败，尝试清理并重新初始化
            try:
                await self.close()
            except Exception:
                pass
            return False
            
    async def _smart_wait(self) -> None:
        """
        智能等待页面加载(异步)
        """
        try:
            # 等待网络空闲
            await self._page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            # 如果网络空闲超时,继续执行
            pass
            
        # 等待一小段时间确保页面稳定
        await asyncio.sleep(0.5)
        
    async def get_content(self) -> str:
        """
        获取页面内容(异步)
        """
        if self._page is None:
            raise RuntimeError("页面未初始化")
            
        return await self._page.content()
        
    async def get_title(self) -> str:
        """
        获取页面标题(异步)
        """
        if self._page is None:
            raise RuntimeError("页面未初始化")
            
        return await self._page.title()
        
    async def evaluate(self, script: str) -> any:
        """
        执行JavaScript(异步)
        """
        if self._page is None:
            raise RuntimeError("页面未初始化")
            
        return await self._page.evaluate(script)
        
    async def screenshot(self, path: str) -> None:
        """
        截图(异步)
        """
        if self._page is None:
            raise RuntimeError("页面未初始化")
            
        await self._page.screenshot(path=path)
        
    async def export_to_pdf(self, path: str) -> None:
        """
        导出PDF(异步)
        """
        if self._page is None:
            raise RuntimeError("页面未初始化")
            
        await self._page.pdf(path=path)
        
    async def close(self) -> None:
        """
        关闭浏览器(异步)
        """
        start_time = time.time()
        
        try:
            if self._page:
                await self._page.close()
                self._page = None
                
            if self._context:
                await self._context.close()
                self._context = None
                
            if self._browser:
                await self._browser.close()
                self._browser = None
                
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
                
            # 记录清理时间
            cleanup_time = time.time() - start_time
            self.metrics.cleanup_count += 1
            self.metrics.avg_cleanup_time = (
                (self.metrics.avg_cleanup_time * (self.metrics.cleanup_count - 1) + cleanup_time)
                / self.metrics.cleanup_count
            )
            
            if self.debug:
                print_info(f"浏览器关闭成功,耗时: {cleanup_time:.2f}s")
                
        except Exception as e:
            self.metrics.cleanup_failures += 1
            print_error(f"关闭浏览器失败: {str(e)}")
            
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start_browser()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        
    @property
    def page(self):
        """获取页面对象"""
        return self._page
        
    @property
    def context(self):
        """获取上下文对象"""
        return self._context
        
    @property
    def browser(self):
        """获取浏览器对象"""
        return self._browser

    # ========== 辅助方法 ==========

    def is_browser_started(self) -> bool:
        """检查浏览器是否已启动"""
        return self._browser is not None and self._page is not None

    def is_page_valid(self) -> bool:
        """
        检查 Page 对象是否有效
        通过尝试访问 Page 的内部连接来判断对象是否仍然可用
        """
        if self._page is None:
            return False
        try:
            # 尝试访问 Page 对象的内部属性，如果对象已失效会抛出异常
            # 这是一个轻量级的检查，不会实际执行任何浏览器操作
            return hasattr(self._page, '_impl_obj') and self._page._impl_obj is not None
        except Exception:
            return False

    async def get_cookies(self) -> List[Dict]:
        """获取所有 cookies（异步）"""
        if self._context is None:
            raise RuntimeError("浏览器上下文未初始化")
        return await self._context.cookies()

    async def add_cookies(self, cookies: List[Dict]) -> None:
        """添加多个 cookies（异步）"""
        if self._context is None:
            raise RuntimeError("浏览器上下文未初始化")
        await self._context.add_cookies(cookies)

    async def add_cookie(self, cookie: Dict) -> None:
        """添加单个 cookie（异步）"""
        if self._context is None:
            raise RuntimeError("浏览器上下文未初始化")
        await self._context.add_cookies([cookie])

    async def cleanup(self) -> None:
        """清理资源（异步）"""
        await self.close()

    async def Close(self) -> None:
        """关闭浏览器（异步，兼容旧代码）"""
        await self.close()
