"""
使用 Playwright 浏览器实现网页导出 PDF 功能

功能特性：
- 支持将网页 URL 转换为 PDF
- 支持将 HTML 内容转换为 PDF
- 支持批量转换多个 URL
- 支持自定义 PDF 格式、边距等选项
- 支持等待特定元素加载
- 支持 Cookie 和自定义请求头
- 自动处理 Windows 平台的 asyncio 事件循环问题

使用示例：
    from tools.mdtools.pdf import url_to_pdf, html_to_pdf, batch_urls_to_pdf
    
    # 1. URL 转 PDF
    url_to_pdf("https://example.com", "./output/example.pdf")
    
    # 2. HTML 转 PDF
    html_content = "<html><body><h1>Hello</h1></body></html>"
    html_to_pdf(html_content, "./output/hello.pdf")
    
    # 3. 批量转换
    urls = ["https://example1.com", "https://example2.com"]
    batch_urls_to_pdf(urls, "./output/")
    
    # 4. 自定义 PDF 选项
    url_to_pdf(
        url="https://example.com",
        output_path="./output/custom.pdf",
        pdf_options={
            'format': 'Letter',
            'margin': {'top': '10mm', 'right': '10mm', 'bottom': '10mm', 'left': '10mm'}
        }
    )

注意事项：
- Windows 平台自动使用 ProactorEventLoop 以支持子进程
- 首次使用需要安装 playwright 浏览器：playwright install chromium
- 默认使用无头模式，可通过 headless=False 显示浏览器窗口
- PDF 生成支持所有浏览器：
  * Chromium: 使用原生 PDF 生成 API（推荐）
  * Firefox/WebKit: 使用截图拼接方式生成 PDF（需要安装 Pillow: pip install Pillow）
"""
import asyncio
import sys
import os
import atexit
from typing import Optional, Dict, Any
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import logging
from driver.chrome_path import get_chrome_executable_path

# Windows 平台需要使用 ProactorEventLoop 以支持子进程
# Playwright 需要启动浏览器子进程，必须使用 ProactorEventLoop
if sys.platform == 'win32':
    # 确保使用 ProactorEventLoop
    if not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class WebToPDFConverter:
    """使用 Playwright 将网页转换为 PDF"""
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False
    
    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",
        timeout: int = 30000,
        wait_time: int = 2000
    ):
        """
        初始化 PDF 转换器
        
        Args:
            headless: 是否使用无头模式
            browser_type: 浏览器类型 (chromium, firefox, webkit)
            timeout: 页面加载超时时间（毫秒）
            wait_time: 页面加载后等待时间（毫秒）
        """
        self.headless = headless
        self.browser_type = browser_type
        self.timeout = timeout
        self.wait_time = wait_time
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
    
    async def _ensure_browser(self) -> Browser:
        """确保浏览器已启动"""
        if self._browser is None:
            # ===== 本地 Chrome 支持（可选，避免强制 playwright install 下载浏览器）=====
            # 仅当通过环境变量 CHROME_EXECUTABLE_PATH 指定（或自动发现到本机标准 Chromium 浏览器）时启用。
            CHROME_PATH = get_chrome_executable_path()
            if CHROME_PATH:
                self.browser_type = "chromium"
            self._playwright = await async_playwright().start()
            launch_kwargs = {"headless": self.headless}
            if self.browser_type == "chromium" and CHROME_PATH:
                launch_kwargs["executable_path"] = CHROME_PATH
            if self.browser_type == "chromium":
                self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            elif self.browser_type == "firefox":
                self._browser = await self._playwright.firefox.launch(headless=self.headless)
            elif self.browser_type == "webkit":
                self._browser = await self._playwright.webkit.launch(headless=self.headless)
            else:
                raise ValueError(f"不支持的浏览器类型: {self.browser_type}")
        return self._browser
    
    async def _create_context(self, **kwargs) -> BrowserContext:
        """创建浏览器上下文"""
        browser = await self._ensure_browser()
        
        # 设置默认的中文语言和中国时区
        default_context_options = {
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
        }
        
        # 合并用户提供的选项（用户选项优先）
        default_context_options.update(kwargs)
        
        self._context = await browser.new_context(**default_context_options)
        return self._context
    
    async def _generate_pdf_from_screenshots(
        self,
        page: Page,
        output_path: str,
        pdf_options: Dict[str, Any]
    ) -> None:
        """
        使用滚动截图方式为 Firefox/WebKit 生成 PDF
        
        Args:
            page: Playwright 页面对象
            output_path: 输出 PDF 路径
            pdf_options: PDF 选项
        """
        try:
            from PIL import Image
            import io
            
            logging.info(f"使用滚动截图模式生成 PDF (浏览器: {self.browser_type})")
            
            # 获取视口尺寸
            viewport = page.viewport_size
            viewport_width = viewport['width'] if viewport else 1280
            viewport_height = viewport['height'] if viewport else 800
            
            # 获取页面完整尺寸
            total_width = await page.evaluate("document.body.scrollWidth")
            total_height = await page.evaluate("document.body.scrollHeight")
            
            logging.info(f"页面尺寸: {total_width}x{total_height}, 视口尺寸: {viewport_width}x{viewport_height}")
            
            # 如果页面宽度大于视口宽度，需要调整视口
            if total_width > viewport_width:
                await page.set_viewport_size({'width': total_width, 'height': viewport_height})
                viewport_width = total_width
                logging.info(f"调整视口宽度为: {viewport_width}")
            
            screenshots = []
            current_y = 0
            
            # 滚动截图
            while current_y < total_height:
                # 滚动到指定位置
                await page.evaluate(f"window.scrollTo(0, {current_y})")
                await page.wait_for_timeout(300)  # 等待滚动完成
                
                # 计算本次截图的高度（剩余高度或视口高度）
                remaining_height = total_height - current_y
                screenshot_height = min(viewport_height, remaining_height)
                
                logging.debug(f"截图位置: y={current_y}, 高度={screenshot_height}")
                
                # 截取当前视口（clip 的 y 坐标是相对于视口的，所以总是从 0 开始）
                if screenshot_height < viewport_height:
                    # 最后一次截图，只截取剩余部分
                    screenshot = await page.screenshot(
                        clip={
                            'x': 0,
                            'y': 0,
                            'width': viewport_width,
                            'height': screenshot_height
                        },
                        type='png'
                    )
                else:
                    # 截取整个视口
                    screenshot = await page.screenshot(
                        clip={
                            'x': 0,
                            'y': 0,
                            'width': viewport_width,
                            'height': viewport_height
                        },
                        type='png'
                    )
                
                # 转换为 PIL Image
                img = Image.open(io.BytesIO(screenshot))
                screenshots.append(img)
                
                # 移动到下一个位置
                current_y += screenshot_height
            
            logging.info(f"共截取 {len(screenshots)} 张图片")
            
            # 合并所有截图
            if screenshots:
                # 计算总高度
                total_img_height = sum(img.height for img in screenshots)
                
                # 创建新图像（使用白色背景）
                merged_img = Image.new('RGB', (viewport_width, total_img_height), 'white')
                
                # 粘贴所有截图
                y_offset = 0
                for idx, img in enumerate(screenshots):
                    merged_img.paste(img, (0, y_offset))
                    y_offset += img.height
                    logging.debug(f"合并图片 {idx + 1}/{len(screenshots)}, 当前偏移: {y_offset}")
                
                # 转换为 PDF
                merged_img.save(output_path, 'PDF', resolution=100.0)
                logging.info(f"滚动截图 PDF 已生成: {output_path} (总高度: {total_img_height}px)")
            else:
                raise ValueError("未能生成任何截图")
                
        except ImportError:
            raise ImportError(
                "使用 Firefox/WebKit 生成 PDF 需要 Pillow 库。"
                "请安装: pip install Pillow"
            )
        except Exception as e:
            logging.error(f"滚动截图生成 PDF 失败: {e}")
            raise
    
    async def _scroll_page_to_load_images(self, page: Page) -> None:
        """
        滚动页面以触发懒加载图片
        
        Args:
            page: Playwright 页面对象
        """
        try:
            logging.info("开始滚动页面以加载图片...")
            
            # 获取页面总高度
            total_height = await page.evaluate("document.body.scrollHeight")
            viewport_height = await page.evaluate("window.innerHeight")
            
            # 如果页面高度小于视口高度，不需要滚动
            if total_height <= viewport_height:
                logging.info("页面内容较少，无需滚动")
                return
            
            # 计算滚动次数（每次滚动一个视口高度）
            scroll_times = int(total_height / viewport_height) + 1
            scroll_delay = 500  # 每次滚动后等待时间（毫秒）
            
            logging.info(f"页面高度: {total_height}px, 视口高度: {viewport_height}px, 需要滚动 {scroll_times} 次")
            
            # 逐步滚动页面
            for i in range(scroll_times):
                # 滚动到指定位置
                scroll_position = (i + 1) * viewport_height
                await page.evaluate(f"window.scrollTo(0, {scroll_position})")
                
                # 等待图片加载
                await page.wait_for_timeout(scroll_delay)
                
                # 检查是否有新的图片加载
                # 等待所有图片开始加载
                try:
                    await page.wait_for_function("""
                        () => {
                            const images = Array.from(document.images);
                            return images.every(img => img.complete || img.naturalHeight > 0);
                        }
                    """, timeout=5000)
                except Exception:
                    # 忽略超时错误，继续滚动
                    pass
            
            # 滚动回顶部
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(500)
            
            # 最后再等待一下，确保所有图片都加载完成
            await page.wait_for_timeout(1000)
            
            logging.info("页面滚动完成，图片加载完毕")
            
        except Exception as e:
            logging.warning(f"滚动页面时出现警告: {e}")
            # 即使滚动失败，也继续执行
    
    async def convert_url_to_pdf(
        self,
        url: str,
        output_path: str,
        wait_for_selector: Optional[str] = None,
        wait_for_load_state: str = "networkidle",
        pdf_options: Optional[Dict[str, Any]] = None,
        page_options: Optional[Dict[str, Any]] = None,
        cookies: Optional[list] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        将网页 URL 转换为 PDF
        
        Args:
            url: 网页 URL
            output_path: 输出 PDF 文件路径
            wait_for_selector: 等待特定元素出现
            wait_for_load_state: 页面加载状态 (load, domcontentloaded, networkidle)
            pdf_options: PDF 生成选项
            page_options: 页面选项（如 viewport, user_agent 等）
            cookies: Cookie 列表
            headers: 请求头
        
        Returns:
            bool: 是否成功
        """
        try:
            # 创建上下文
            context_options = page_options or {}
            if headers:
                context_options['extra_http_headers'] = headers
            
            context = await self._create_context(**context_options)
            
            # 添加 cookies
            if cookies:
                await context.add_cookies(cookies)
            
            # 创建页面
            page = await context.new_page()
            
            try:
                # 访问 URL
                logging.info(f"正在访问: {url}")
                await page.goto(url, timeout=self.timeout, wait_until=wait_for_load_state)
                
                # 等待特定元素
                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=self.timeout)
                
                # 针对微信公众号文章的特殊处理
                if 'mp.weixin.qq.com' in url:
                    try:
                        # 移除微信公众号底部工具栏
                        await page.evaluate("""
                            const bottomBar = document.getElementById('js_article_bottom_bar');
                            if (bottomBar) {
                                bottomBar.remove();
                            }
                        """)
                        logging.info("已移除微信公众号底部工具栏")
                    except Exception as e:
                        logging.warning(f"移除微信公众号底部工具栏失败: {e}")
                
                # 滚动页面以触发图片加载
                await self._scroll_page_to_load_images(page)
                
                # 额外等待时间
                if self.wait_time > 0:
                    await page.wait_for_timeout(self.wait_time)
                
                # 准备 PDF 选项
                default_pdf_options = {
                    'format': 'A4',
                    'print_background': True,
                    'margin': {
                        'top': '20mm',
                        'right': '20mm',
                        'bottom': '20mm',
                        'left': '20mm'
                    }
                }
                
                if pdf_options:
                    default_pdf_options.update(pdf_options)
                
                # 确保输出目录存在
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                # 生成 PDF
                if self.browser_type == "chromium":
                    # Chromium 支持原生 PDF 生成
                    await page.pdf(path=output_path, **default_pdf_options)
                else:
                    # Firefox 和 WebKit 使用截图方式生成 PDF
                    await self._generate_pdf_from_screenshots(page, output_path, default_pdf_options)
                
                logging.info(f"PDF 已生成: {output_path}")
                return True
                
            finally:
                await page.close()
                await context.close()
                
        except Exception as e:
            logging.error(f"转换 PDF 失败: {e}")
            return False
    
    async def convert_html_to_pdf(
        self,
        html_content: str,
        output_path: str,
        base_url: Optional[str] = None,
        pdf_options: Optional[Dict[str, Any]] = None,
        page_options: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        将 HTML 内容转换为 PDF
        
        Args:
            html_content: HTML 内容
            output_path: 输出 PDF 文件路径
            base_url: 基础 URL（用于解析相对路径）
            pdf_options: PDF 生成选项
            page_options: 页面选项
        
        Returns:
            bool: 是否成功
        """
        try:
            # 创建上下文
            context = await self._create_context(**(page_options or {}))
            page = await context.new_page()
            
            try:
                # 设置 HTML 内容
                await page.set_content(html_content, wait_until="networkidle", timeout=self.timeout)
                
                # 滚动页面以触发图片加载
                await self._scroll_page_to_load_images(page)
                
                # 额外等待时间
                if self.wait_time > 0:
                    await page.wait_for_timeout(self.wait_time)
                
                # 准备 PDF 选项
                default_pdf_options = {
                    'format': 'A4',
                    'print_background': True,
                    'margin': {
                        'top': '20mm',
                        'right': '20mm',
                        'bottom': '20mm',
                        'left': '20mm'
                    }
                }
                
                if pdf_options:
                    default_pdf_options.update(pdf_options)
                
                # 确保输出目录存在
                output_file = Path(output_path)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                # 生成 PDF
                if self.browser_type == "chromium":
                    # Chromium 支持原生 PDF 生成
                    await page.pdf(path=output_path, **default_pdf_options)
                else:
                    # Firefox 和 WebKit 使用截图方式生成 PDF
                    await self._generate_pdf_from_screenshots(page, output_path, default_pdf_options)
                
                logging.info(f"PDF 已生成: {output_path}")
                return True
                
            finally:
                await page.close()
                await context.close()
                
        except Exception as e:
            logging.error(f"转换 PDF 失败: {e}")
            return False
    
    async def convert_multiple_urls(
        self,
        urls: list,
        output_dir: str,
        filename_template: str = "page_{index}.pdf",
        **kwargs
    ) -> Dict[str, bool]:
        """
        批量转换多个 URL 为 PDF
        
        Args:
            urls: URL 列表
            output_dir: 输出目录
            filename_template: 文件名模板
            **kwargs: 其他参数传递给 convert_url_to_pdf
        
        Returns:
            Dict[str, bool]: URL 到转换结果的映射
        """
        results = {}
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for index, url in enumerate(urls):
            filename = filename_template.format(index=index + 1, url=url)
            output_file = output_path / filename
            success = await self.convert_url_to_pdf(url, str(output_file), **kwargs)
            results[url] = success
        
        return results
    
    async def close(self):
        """关闭浏览器"""
        try:
            if self._context:
                await self._context.close()
                self._context = None
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logging.warning(f"关闭浏览器时出现警告: {e}")


# 同步包装函数
def _run_async(coro):
    """安全地运行异步协程"""
    # 使用 asyncio.run() 来确保正确的事件循环管理
    # Python 3.7+ 的 asyncio.run() 会自动处理事件循环的创建和清理
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # 如果在已有事件循环中运行，使用备用方案
        logging.warning(f"检测到事件循环冲突，使用备用方案: {e}")
        
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(coro)
            return result
        finally:
            # 清理待处理的任务
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as e:
                logging.debug(f"清理任务时出现异常: {e}")
            finally:
                # 关闭异步生成器
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                
                # 关闭事件循环
                loop.close()
                asyncio.set_event_loop(None)


def url_to_pdf(
    url: str,
    output_path: str,
    headless: bool = True,
    browser_type: str = "chromium",
    timeout: int = 30000,
    wait_time: int = 2000,
    wait_for_selector: Optional[str] = None,
    pdf_options: Optional[Dict[str, Any]] = None,
    page_options: Optional[Dict[str, Any]] = None,
    cookies: Optional[list] = None,
    headers: Optional[Dict[str, str]] = None
) -> bool:
    """
    将网页 URL 转换为 PDF（同步版本）
    
    Args:
        url: 网页 URL
        output_path: 输出 PDF 文件路径
        headless: 是否使用无头模式
        browser_type: 浏览器类型
        timeout: 超时时间
        wait_time: 等待时间
        wait_for_selector: 等待选择器
        pdf_options: PDF 选项
        page_options: 页面选项
        cookies: Cookie 列表
        headers: 请求头
    
    Returns:
        bool: 是否成功
    """
    async def _convert():
        async with WebToPDFConverter(
            headless=headless,
            browser_type=browser_type,
            timeout=timeout,
            wait_time=wait_time
        ) as converter:
            return await converter.convert_url_to_pdf(
                url=url,
                output_path=output_path,
                wait_for_selector=wait_for_selector,
                pdf_options=pdf_options,
                page_options=page_options,
                cookies=cookies,
                headers=headers
            )
    
    return _run_async(_convert())


def html_to_pdf(
    html_content: str,
    output_path: str,
    headless: bool = True,
    browser_type: str = "chromium",
    timeout: int = 30000,
    wait_time: int = 2000,
    pdf_options: Optional[Dict[str, Any]] = None,
    page_options: Optional[Dict[str, Any]] = None
) -> bool:
    """
    将 HTML 内容转换为 PDF（同步版本）
    
    Args:
        html_content: HTML 内容
        output_path: 输出 PDF 文件路径
        headless: 是否使用无头模式
        browser_type: 浏览器类型
        timeout: 超时时间
        wait_time: 等待时间
        pdf_options: PDF 选项
        page_options: 页面选项
    
    Returns:
        bool: 是否成功
    """
    async def _convert():
        async with WebToPDFConverter(
            headless=headless,
            browser_type=browser_type,
            timeout=timeout,
            wait_time=wait_time
        ) as converter:
            return await converter.convert_html_to_pdf(
                html_content=html_content,
                output_path=output_path,
                pdf_options=pdf_options,
                page_options=page_options
            )
    
    return _run_async(_convert())


def batch_urls_to_pdf(
    urls: list,
    output_dir: str,
    headless: bool = True,
    browser_type: str = "chromium",
    timeout: int = 30000,
    wait_time: int = 2000,
    filename_template: str = "page_{index}.pdf",
    **kwargs
) -> Dict[str, bool]:
    """
    批量转换多个 URL 为 PDF（同步版本）
    
    Args:
        urls: URL 列表
        output_dir: 输出目录
        headless: 是否使用无头模式
        browser_type: 浏览器类型
        timeout: 超时时间
        wait_time: 等待时间
        filename_template: 文件名模板
        **kwargs: 其他参数
    
    Returns:
        Dict[str, bool]: URL 到转换结果的映射
    """
    async def _convert():
        async with WebToPDFConverter(
            headless=headless,
            browser_type=browser_type,
            timeout=timeout,
            wait_time=wait_time
        ) as converter:
            return await converter.convert_multiple_urls(
                urls=urls,
                output_dir=output_dir,
                filename_template=filename_template,
                **kwargs
            )
    
    return _run_async(_convert())


if __name__ == "__main__":
    # 测试代码
    import os
    
    # 确保输出目录存在
    os.makedirs("./data", exist_ok=True)
    
    try:
        urls=[
            "https://mp.weixin.qq.com/s/0Bzw7AY754tDT9anJtsSCw",
            "http://127.0.0.1:8001/views/print/FEATURED_ARTICLES-CFyDBjG1qwm3YtyL8kkR7g"
        ]
        print("开始测试 PDF 转换...")
        for i,url in enumerate(urls):
            pdf_file=f"./data/test_{i}.pdf"
            success = url_to_pdf(url, pdf_file,browser_type="webkit")
            from pdf_extractor import pdf_to_docx
            pdf_to_docx(pdf_file,f"{pdf_file.replace('.pdf','.docx')}")
            if success:
                print(f"{url}✓ PDF 转换成功！")
            else:
                print(f"{url}✗ PDF 转换失败")
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()