from asyncio import wait_for
from socket import timeout
import sys

from sqlalchemy import False_

import driver
from .playwright_driver import PlaywrightController
from PIL import Image
from driver.success import Success
import time
import os
from driver.success import getStatus
from driver.store import Store
import re
from threading import Timer, Lock
from .cookies import expire
import json
import psutil
from core.print import print_error,print_warning,print_info,print_success
class Wx:
    _haslogin=False
    SESSION=None
    HasCode=False
    isLOCK=False
    WX_LOGIN="https://mp.weixin.qq.com/"
    WX_HOME="https://mp.weixin.qq.com/cgi-bin/home"
    wx_login_url="static/wx_qrcode.png"
    lock_file_path="data/lock.lock"
    CallBack=None
    Notice=None
    ext_data = None
    # 添加线程锁保护共享变量
    _login_lock = Lock()
    def __init__(self):
        self.lock_path=os.path.dirname(self.lock_file_path)
        self.refresh_interval=3660*24
        self.controller=PlaywrightController()
        if not os.path.exists(self.lock_path):
            os.makedirs(self.lock_path)
        self.Clean()
        self.release_lock()
        pass

    def GetHasCode(self):
        if os.path.exists(self.wx_login_url):
            return True
        return False
    async def extract_token_from_requests(self):
        """从页面中提取token（异步）"""
        try:
            # 优先使用临时控制器，其次使用默认控制器
            controller = getattr(self, '_temp_controller', None) or self.controller

            if not controller or not controller.page:
                return None

            page = controller.page
            # 尝试从当前URL获取token
            current_url = page.url
            token_match = re.search(r'token=([^&]+)', current_url)
            if token_match:
                return token_match.group(1)

            # 尝试从localStorage获取
            token = await page.evaluate("() => localStorage.getItem('token')")
            if token:
                return token

            # 尝试从sessionStorage获取
            token = await page.evaluate("() => sessionStorage.getItem('token')")
            if token:
                return token

            # 尝试从cookie获取
            cookies = await page.context.cookies()
            for cookie in cookies:
                if 'token' in cookie['name'].lower():
                    return cookie['value']

            return ''
        except Exception as e:
            print(f"提取token时出错: {str(e)}")
            return ''
    async def switch_account(self, username: str = "", progress_callback=None):
        """切换账号功能（异步）

        Args:
            username: 目标账号的用户名，如果为空则切换到其他可用账号
            progress_callback: 可选回调，签名 ``callback(stage: str, message: str, progress: int) -> None``，
                用于将进度广播到前端（SSE / 轮询）。
        """
        import asyncio

        def report(stage: str, message: str, progress: int = 0) -> None:
            if progress_callback is not None:
                try:
                    progress_callback(stage, message, progress)
                except Exception:
                    pass

        print("开始切换账号...")
        report("queued", "任务开始", 0)
        main_queue_was_running = False
        content_queue_was_running = False

        try:
            # 暂停主队列和内容队列，等待当前任务完成
            from core.queue import TaskQueue, ContentTaskQueue
            main_queue_was_running = TaskQueue._is_running
            content_queue_was_running = ContentTaskQueue._is_running

            report("stopping_queues", "暂停抓取队列", 5)
            # 停止队列
            if main_queue_was_running:
                print_info("暂停主任务队列...")
                TaskQueue.stop()
            if content_queue_was_running:
                print_info("暂停内容任务队列...")
                ContentTaskQueue.stop()

            # 等待当前任务真正完成 — 通过配置可缩短；默认仍 120s 以保证抓取原子性
            import os
            try:
                max_wait = int(os.getenv("SWITCH_MAX_WAIT", "120"))
            except Exception:
                max_wait = 120
            wait_interval = 1
            waited = 0

            while waited < max_wait:
                has_current_task = False

                # 检查主队列是否有正在执行的任务
                if TaskQueue._current_task is not None:
                    has_current_task = True
                    print_info(f"主队列任务正在执行: {TaskQueue._current_task.task_name}")

                # 检查内容队列是否有正在执行的任务
                if ContentTaskQueue._current_task is not None:
                    has_current_task = True
                    print_info(f"内容队列任务正在执行: {ContentTaskQueue._current_task.task_name}")

                if not has_current_task:
                    print_success("所有任务已完成，可以安全切换账号")
                    break

                if waited % 5 == 0 and waited > 0:
                    report("stopping_queues", f"等待任务完成中（{waited}/{max_wait}s）", 5 + min(20, waited // 6))
                await asyncio.sleep(wait_interval)
                waited += wait_interval

            if waited >= max_wait:
                print_warning("等待超时，仍有任务未完成，切换账号可能导致会话失效")
                report("stopping_queues", f"队列等待超时，继续尝试（{waited}s）", 25)

            report("checking_token", "检查 Token 有效性", 30)
            await self.Token(isClose=False)
            if getStatus() is False:
                # 提前暴露结果，不阻塞 60s；让前端用 UI 引导用户重新扫码
                print_warning("Token 已过期，请重新扫码登录")
                from jobs.failauth import send_wx_code
                send_wx_code("账号过期，请重新扫码登录")
                report("failed", "Token 已过期，请调用 /auth/wechat/unbind 后重新扫码", 100)
                return False
            await asyncio.sleep(1)

            # 检查 controller 和 Page 对象是否有效；若不存在则回退到重新启动浏览器
            if not hasattr(self, 'controller') or self.controller is None:
                print_warning("Controller 未初始化，正在重新创建浏览器...")
                self.controller = PlaywrightController()

            if not self.controller.is_page_valid() or self.controller.page is None:
                report("starting_browser", "浏览器 Page 无效，正在重新打开公众平台…", 40)
                print_warning("Page 对象无效或为 None，正在重新打开浏览器并导航到公众平台...")
                try:
                    await self.controller.start_browser()
                    await self.controller.open_url(self.WX_LOGIN)
                    # 网络空闲等待超时后继续；后续点击操作再处理是否需要登录
                    try:
                        await self.controller.page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    await asyncio.sleep(2)
                except Exception as e:
                    print_error(f"重新打开浏览器失败: {str(e)}，无法切换账号")
                    report("failed", f"启动浏览器失败: {e}", 100)
                    return False

            page = self.controller.page
            if page is None:
                print_error("Page 对象仍为 None，无法切换账号")
                report("failed", "无法获取 Page 对象", 100)
                return False

            # 等待页面加载完成，添加异常处理
            report("starting_browser", "等待公众平台首页加载…", 55)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                print_warning(f"等待页面加载状态失败: {str(e)}，继续尝试切换账号...")

            # 点击账号信息区域打开账号面板
            report("clicking", "打开账号面板…", 65)
            account_info = page.locator(".weui-desktop-account__info")
            if await account_info.count() > 0:
                await account_info.click()
                await asyncio.sleep(1)

                # 等待账号面板显示
                account_panel = page.locator(".account_box-panel")
                if await account_panel.count() > 0:
                    # 查找切换账号按钮（更精确的选择器）
                    switch_account_link = account_panel.locator("li.account_box-panel-item:has-text('切换账号') a")
                    if await switch_account_link.count() > 0:
                        print_info("找到切换账号按钮，点击切换...")
                        await switch_account_link.click()
                        await asyncio.sleep(3)

                        try:
                            # 查找可切换的账号（排除当前登录账号）
                            accounts = page.locator(
                                                ".switch-account-dialog .switch-account-dialog_section:has-text('公众号') .section-item:not(:has-text('当前登录')),"
                                                ".switch-account-dialog .switch-account-dialog_section:has-text('服务号') .section-item:not(:has-text('当前登录'))"
                                            )
                            account_count = await accounts.count()
                            print(f"当前一共有{account_count}个可切换账号")
                            import random
                            if account_count > 0:
                                report("clicking", f"找到 {account_count} 个可切换账号，正在选择…", 75)
                                # 点击第一个可切换的账号
                                random_index = random.randint(0, account_count - 1)
                                await asyncio.sleep(1)
                                p = accounts.nth(random_index).locator("p")
                                nick_name = accounts.nth(random_index).locator(".section-item__nickname")
                                account_id = await p.text_content()
                                account_name = await nick_name.text_content()
                                print(f"账号: {account_name} ID:{account_id}")
                                await p.click()
                                # 等待页面加载并验证切换成功，添加异常处理
                                try:
                                    await page.wait_for_load_state("networkidle", timeout=10000)
                                except Exception as e:
                                    print_warning(f"等待页面加载状态失败: {str(e)}，继续验证切换结果...")
                                await asyncio.sleep(2)
                                session_data = await self.Call_Success(has_extdata=False)

                                await self.Token(isClose=False)
                                print_success("账号切换成功")
                                from jobs.notice import sys_notice
                                from core.config import cfg
                                try:
                                    cookies = await self.controller.get_cookies()
                                    exp = self.format_token(cookies)
                                    exp_time = exp["expiry"]["expiry_time"]
                                    token = exp["token"]
                                except Exception as e:
                                    print_error(e)
                                    exp_time = "-"
                                    token = "-"
                                    pass
                                # 添加延迟，避免 Playwright memoryview 缓冲区问题
                                await asyncio.sleep(0.5)
                                sys_notice(f"账号切换成功\n- 账号名称: {account_name} \n- 账号ID: {account_id} \n - Token: {token} \n- 过期时间: {exp_time}", str(cfg.get("server.code_title","WeRss账号切换成功")))
                                report("done", f"切换成功：{account_name}", 100)
                                return True
                            else:
                                print_warning("没有找到可切换的账号")
                                report("failed", "没有可切换的账号（只剩当前登录账号）", 100)
                                return False
                        except Exception as e:
                            print_error(f"切换账号时发生错误: {str(e)}")
                            report("failed", f"切换错误: {e}", 100)
                            return False
                    else:
                        print_warning("未找到切换账号按钮")
                        report("failed", "未找到切换账号按钮（公众平台改版？）", 100)
                        return False
                else:
                    print_warning("账号面板未打开")
                    report("failed", "账号面板未打开", 100)
                    return False
            else:
                print_warning("未找到账号信息区域")
                # 选择器 miss：兜底触发 QR 流（仅本地接口返回 ok=False，让前端引导重新扫码）
                report("failed", "未找到账号信息区域，请重新扫码授权", 100)
                return False

        except Exception as e:
            print_error(f"切换账号时发生错误: {str(e)}")
            report("failed", f"切换错误: {e}", 100)
            return False
        finally:
            # 恢复任务队列
            try:
                from core.queue import TaskQueue, ContentTaskQueue
                print_info(f"准备恢复队列: 主队列={main_queue_was_running}, 内容队列={content_queue_was_running}")
                if main_queue_was_running:
                    print_info("恢复主任务队列...")
                    TaskQueue.run_task_background()
                    print_success("主任务队列已恢复")
                if content_queue_was_running:
                    print_info("恢复内容任务队列...")
                    ContentTaskQueue.run_task_background()
                    print_success("内容任务队列已恢复")
            except Exception as e:
                print_error(f"恢复队列失败: {e}")
    def GetCode(self,CallBack=None,Notice=None):
        self.Notice=Notice
        if  self.check_lock():
            print_warning("微信公众平台登录脚本正在运行，请勿重复运行")
            return {
                "code":f"{self.wx_login_url}?t={(time.time())}",
                "msg":"微信公众平台登录脚本正在运行，请勿重复运行！"}

        self.Clean()
        print("子线程执行中")

        def run_wxLogin():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.wxLogin(CallBack, True))
            finally:
                loop.close()

        from core.thread import ThreadManager
        self.thread = ThreadManager(target=run_wxLogin)
        self.thread.start()  # 启动线程
        from core.ver import VERSION
        print(f"微信公众平台登录 v{VERSION}")
        return WX_API.QRcode()
    
    wait_time=1
    def QRcode(self):
        return {
            "code":f"/{self.wx_login_url}?t={(time.time())}",
            "is_exists":self.GetHasCode(),
        }
    async def refresh_task(self):
        try:
            await self.controller.page.reload()
            await self.Call_Success()
            # 检查登录状态
            if "home" not in self.controller.page.url:
                print("检测到登录已过期，请重新登录")
                raise Exception(f"登录已经失效，请重新登录")
        except Exception as e:
            raise Exception(f"浏览器关闭")  # 重新抛出异常以便外部捕获处理
    def QrStatus(self):
        return {"login_status":self.HasLogin(),"qr_code":self.GetHasCode()}

    def HasLogin(self):
        with self._login_lock:
            return self._haslogin
    async def schedule_refresh(self):
        import asyncio

        if self.refresh_interval <= 0:
            return

        with self._login_lock:
            if not self._haslogin or not hasattr(self, 'controller') or self.controller is None:
                return

        try:
            await self.refresh_task()
            # 使用守护线程避免资源泄露
            async def schedule_next():
                await asyncio.sleep(self.refresh_interval)
                await self.schedule_refresh()

            # 在后台启动下一次刷新
            asyncio.create_task(schedule_next())
        except Exception as e:
            print_error(f"定时刷新任务失败: {str(e)}")
            # 不再抛出异常，避免无限循环
    async def Token(self, callback=None, isClose=True):
        """使用token登录（异步）

        Args:
            callback: 登录成功回调函数
            isClose: 是否在完成后关闭浏览器

        Returns:
            登录成功返回session数据,失败返回None或False
        """
        import asyncio

        try:
            self.CallBack = callback
            if not getStatus():
                print_warning("登录状态检查失败")
                return None

            from driver.token import get as get_val
            token = str(get_val("token", ""))
            if not token:
                print_warning("未找到有效的token")
                return None

            # 复用已有的controller实例,避免重复创建
            if not hasattr(self, 'controller') or self.controller is None:
                self.controller = PlaywrightController()

            controller = self.controller
            # 保存到临时变量，让 Call_Success 和 _extract_wechat_data 能使用
            self._temp_controller = controller

            # 检查浏览器是否已启动且 Page 对象有效
            if not controller.is_browser_started() or not controller.is_page_valid():
                print_info("浏览器未启动或 Page 对象无效，正在启动...")
                await controller.start_browser()

                cookie = Store.load()
                if cookie:
                    # 为每个cookie添加必要的domain字段
                    for c in cookie:
                        if 'domain' not in c:
                            c['domain'] = 'mp.weixin.qq.com'
                        if 'path' not in c:
                            c['path'] = '/'
                    await controller.add_cookies(cookie)

            # 打开URL前再次检查 Page 对象有效性
            if not controller.is_page_valid():
                print_error("Page 对象仍然无效，无法继续")
                return False

            await controller.open_url(f"{self.WX_HOME}?t=home/index&lang=zh_CN&token={token}")
            page = controller.page

            # 验证 page 对象是否有效
            if page is None:
                print_error("Page 对象为 None，无法继续操作")
                return False

            qrcode = page.locator("#jumpUrl")
            await qrcode.wait_for(state="visible", timeout=self.wait_time * 1000)
            await qrcode.click()
            await asyncio.sleep(2)
            hasLogin = page.locator("body:has-text('使用账号登录')")
            if await hasLogin.count() > 0:
                self._haslogin = False
                from jobs.failauth import send_wx_code
                import threading
                threading.Thread(target=send_wx_code,args=(f"公众号平台登录失效,请重新登录",)).start()
                return False
            return await self.Call_Success()
        except ImportError as e:
            print_error(f"导入模块失败: {str(e)}")
            return False
        except Exception as e:
            print_error(f"Token操作失败: {str(e)}")
            return False
        finally:
            # 清理临时控制器引用
            self._temp_controller = None
            # 只在明确要求关闭时才清理
            if isClose:
                try:
                    if hasattr(self, 'controller') and self.controller:
                        await self.controller.cleanup()
                except Exception:
                    pass
    def isLock(self):             
        if self.isLock:
            if os.path.exists(self.wx_login_url):
                try:
                    size=os.path.getsize(self.wx_login_url)
                    return size>364
                except Exception as e:
                    print(f"二维码图片获取失败: {str(e)}")
        return self.isLock
    async def _wait_qrcode_ready(self, page, qr_tag, timeout=30):
        """等待登录二维码图片加载完成（异步）

        新版登录页可能默认展示"微信快捷登录"（open.weixin.qq.com iframe），
        此时经典二维码处于隐藏状态且src为空，直接截图会得到空白图片或超时。
        检测到该情况时点击"扫码登录"链接切换回二维码登录，
        再等待二维码图片可见且真正加载完成。
        """
        import asyncio

        deadline = time.time() + timeout
        switch_clicked = False
        while time.time() < deadline:
            ready = await page.evaluate(
                """(sel) => {
                    const img = document.querySelector(sel);
                    if (!img) return false;
                    const style = window.getComputedStyle(img);
                    if (style.display === 'none' || style.visibility === 'hidden') return false;
                    return !!img.src && img.complete && img.naturalWidth > 50;
                }""", qr_tag)
            if ready:
                return True
            if not switch_clicked:
                switch_link = page.locator("a.login__type__container__link_text", has_text="扫码登录")
                if await switch_link.count() > 0 and await switch_link.first.is_visible():
                    print_info("检测到快捷登录页面，切换到扫码登录...")
                    await switch_link.first.click()
                    switch_clicked = True
            await asyncio.sleep(0.5)
        return False

    async def wxLogin(self, CallBack=None, NeedExit=True):
        """
        微信公众平台登录流程（异步）：
        1. 检查依赖和环境
        2. 打开微信公众平台
        3. 全屏截图保存二维码
        4. 等待用户扫码登录
        5. 获取登录后的cookie和token
        6. 启动定时刷新线程(默认30分钟刷新一次)
        """
        import asyncio

        # 使用上下文管理器确保资源清理
        try:
            if self.check_lock():
                print_warning("微信公众平台登录脚本正在运行，请勿重复运行")
                return None

            self.set_lock()

            # 使用更短的锁持有时间，只保护变量修改
            self._login_lock.acquire()
            self._haslogin = False
            self._login_lock.release()

            # 清理现有资源
            self.cleanup_resources()

            self.controller = PlaywrightController()
            # 初始化浏览器控制器
            driver = self.controller
            # 启动浏览器并打开微信公众平台
            print_info("正在启动浏览器...")
            await driver.start_browser()
            await driver.open_url(self.WX_LOGIN)
            page = driver.page

            # 等待页面完全加载
            # 新版登录页存在持续的轮询请求，networkidle可能永远不触发，
            # 超时不视为错误，由后续二维码加载检测兜底
            print_info("正在加载登录页面...")
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            # 定位二维码区域
            qr_tag = ".login__type__container__scan__qrcode"
            # 新版登录页可能默认展示"微信快捷登录"，二维码被隐藏或src为空，
            # 需要先切换回扫码登录并等待二维码图片真正加载完成
            if not await self._wait_qrcode_ready(page, qr_tag):
                raise Exception("二维码加载超时，请重试")
            # 获取二维码图片URL
            qrcode = await page.query_selector(qr_tag)
            code_src = await qrcode.get_attribute("src")
            print("正在生成二维码图片...")
            print(f"code_src:{code_src}")

            # 使用Playwright截图功能（添加异常处理）
            await qrcode.screenshot(path=self.wx_login_url)

            print("二维码已保存为 wx_qrcode.png，请扫码登录...")
            self.HasCode = True
            if os.path.getsize(self.wx_login_url) <= 364:
                raise Exception("二维码图片获取失败，请重新扫码")
            # 等待登录成功（检测二维码图片加载完成）
            print("等待扫码登录...")
            if self.Notice is not None:
                self.Notice()

            # 监听页面导航事件
            def handle_frame_navigated(frame):
                current_url = frame.url
                if self.WX_HOME in current_url:
                    print(f"登录成功，正在获取cookie和token...")
            page.on('framenavigated', handle_frame_navigated)
            # 只等待主页面跳转到公众平台首页，
            # 不能用 wait_for_event("framenavigated")：页面内的快捷登录iframe
            # 加载时也会触发该事件，导致未扫码就误判为登录成功
            await page.wait_for_url(lambda url: "cgi-bin/home" in url, timeout=5*60 * 1000)

            from .success import setStatus
            with self._login_lock:
                self._haslogin = True
            setStatus(True)
            self.CallBack = CallBack
            await self.Call_Success()
        except Exception as e:
            if "Timeout" in str(e):
                print_warning("\n扫码登录超时，请重新运行程序进行扫码登录")

            else:
                print_error(f"\n错误发生: {str(e)}")
            self.SESSION = None
            return self.SESSION
        finally:
            self.release_lock()
            if NeedExit:
                self.Clean()
            await self.Close()
        return self.SESSION
    def format_token(self, cookies: list, token: str = ""):
        cookies_str=""
        for cookie in cookies:
            # print(f"{cookie['name']}={cookie['value']}")
            cookies_str+=f"{cookie['name']}={cookie['value']}; "
            if 'token' in cookie['name'].lower():
                token= token or cookie['value']
        # 计算 slave_sid cookie 有效时间
        cookie_expiry = expire(cookies)
        return{
                'cookies': cookies,
                'cookies_str': cookies_str,
                'token': token,
                'wx_login_url': self.wx_login_url,
                'expiry': cookie_expiry
            }
    async def Call_Success(self, has_extdata=True):
        """处理登录成功后的回调逻辑（异步）"""
        # 优先使用临时控制器（用于多线程场景），其次使用默认控制器
        controller = getattr(self, '_temp_controller', None) or self.controller
        if controller is None:
            print_error("浏览器控制器未初始化")
            return None

        # 获取token
        token = await self.extract_token_from_requests()

        # 获取当前所有cookie
        cookies = await controller.get_cookies()
        # print("\n获取到的Cookie:")
        self.SESSION = self.format_token(cookies, str(token))
        with self._login_lock:
            self._haslogin = False if self.SESSION["expiry"] is None else True
        # 登录成功后不立即清理二维码，保持浏览器运行
        if self._haslogin:
            try:
                # 使用更健壮的选择器定位元素
                if has_extdata:
                    self.ext_data = await self._extract_wechat_data()
            except Exception as e:
                print_error(f"获取公众号信息失败: {str(e)}")
                self.ext_data = None
            Store.save(cookies)
            # 保存新的 token 和 cookie
            if self.SESSION and self.SESSION.get("token"):
                from driver.token import set_token
                set_token(self.SESSION, self.ext_data)
                print_success(f"已更新Token: {self.SESSION.get('token')}")
            print_success("登录成功！")
        else:
            print_warning("未登录！")

        # print(cookie_expiry)
        if self.CallBack is not None:
            self.CallBack(self.SESSION, self.ext_data)

        return self.SESSION 

    async def _extract_wechat_data(self):
        """提取微信公众号数据，使用更健壮的选择器（异步）"""
        # 优先使用临时控制器，其次使用默认控制器
        controller = getattr(self, '_temp_controller', None) or self.controller

        if not controller or not controller.page:
            return {}

        page = controller.page
        data = {}

        # 使用更健壮的选择器，增加备选方案
        selectors = {
            "wx_app_name": [".weui-desktop_name", ".acount_box-nickname", ".account_box-panel-head__nickname"],
            "wx_logo": [".weui-desktop-account__img", ".weui-desktop-account__thumb", ".account_box-panel-head__thumb"],
            "wx_read_yesterday": [".weui-desktop-data-overview:nth-child(1) .weui-desktop-data-overview__desc span", ".weui-desktop-data-overview:first-child .weui-desktop-data-overview__desc span"],
            "wx_share_yesterday": [".weui-desktop-data-overview:nth-child(2) .weui-desktop-data-overview__desc span", ".weui-desktop-data-overview:nth-child(1) + .weui-desktop-data-overview .weui-desktop-data-overview__desc span"],
            "wx_watch_yesterday": [".weui-desktop-data-overview:nth-child(3) .weui-desktop-data-overview__desc span", ".weui-desktop-data-overview:last-child .weui-desktop-data-overview__desc span"],
            "wx_yuan_count": [".original_cnt .weui-desktop-user_sum span", ".weui-desktop-user_sum.original_cnt span"],
            "wx_user_count": [".weui-desktop-user_sum:not(.original_cnt) span", ".weui-desktop-user_num .weui-desktop-user_sum span"]
        }

        for key, selector_list in selectors.items():
            data[key] = ""
            selector_found = False

            # 遍历备选选择器
            for selector in selector_list:
                try:
                    element = page.locator(selector)
                    # 先检查元素是否存在，再等待可见
                    if await element.count() > 0:
                        await element.wait_for(state="visible", timeout=2000)
                        if key == "wx_logo":
                            data[key] = await element.get_attribute("src")
                        else:
                            data[key] = await element.text_content()
                        selector_found = True
                        # print_info(f"成功获取{key}，使用选择器: {selector}")
                        break
                except Exception as e:
                    continue

            if not selector_found:
                print_warning(f"获取{key}失败: 所有选择器都无法定位到元素")
                # 对于特定字段，尝试更通用的方法
                if key == "wx_watch_yesterday":
                    try:
                        # 尝试获取所有.data-item .number元素
                        all_numbers = page.locator(".data-item .number")
                        count = await all_numbers.count()
                        if count >= 3:
                            data[key] = await all_numbers.nth(2).text_content()
                            print_info(f"使用通用方法获取{key}成功")
                        elif count > 0:
                            # 如果只有1-2个，取最后一个
                            data[key] = await all_numbers.nth(count-1).text_content()
                            print_info(f"使用备用方法获取{key}成功")
                    except Exception as fallback_e:
                        print_error(f"备用方法也失败: {str(fallback_e)}")

        return data
    
    def cleanup_resources(self):
        """清理所有相关资源"""
        try:
            # 清理临时文件
            self.Clean()
                
            # 重置状态
            with self._login_lock:
                self._haslogin = False
                self.HasCode = False
                
            print_info("资源清理完成")
            return True
        except Exception as e:
            return False

    async def Close(self):
        rel = False
        try:
            if hasattr(self, 'controller') and self.controller is not None:
                await self.controller.Close()
                rel = True
        except Exception as e:
            print_warning("浏览器未启动或已关闭")
            pass
        return rel
    def Clean(self):
        try:
            os.remove(self.wx_login_url)
        except:
            pass
        finally:
           pass
           
    def expire_all_cookies(self):
        """设置所有cookie为过期状态"""
        try:
            if hasattr(self, 'controller') and hasattr(self.controller, 'context'):
                self.controller.context.clear_cookies()
                return True
            else:
                print("浏览器未启动，无法操作cookie")
                return False
        except Exception as e:
            print(f"设置cookie过期时出错: {str(e)}")
            return False
            
    def check_lock(self, timeout: int = 300) -> bool:
        if not os.path.exists(self.wx_login_url):
            return False
        return True
    def set_lock(self):
        """创建锁定文件，写入当前进程PID和时间戳"""
        os.makedirs(os.path.dirname(self.lock_file_path), exist_ok=True)
        current_pid = os.getpid()
        with open(self.lock_file_path, 'w') as f:
            f.write(f"{current_pid}|{time.time()}")
        self.isLOCK = True
        
    def release_lock(self):
        """删除锁定文件"""
        try:
            # 只释放当前进程持有的锁
            if os.path.exists(self.lock_file_path):
                with open(self.lock_file_path, 'r') as f:
                    content = f.read().strip()
                parts = content.split('|')
                if parts and int(parts[0]) == os.getpid():
                    os.remove(self.lock_file_path)
            self.isLOCK = False
            return True
        except Exception:
            return False
    
    def _force_release_lock(self):
        """强制释放锁（用于清理过期或损坏的锁）"""
        try:
            if os.path.exists(self.lock_file_path):
                os.remove(self.lock_file_path)
        except Exception:
            pass


WX_API = Wx()
def GetCode(CallBack:any=None,NeedExit=True):
    WX_API.GetCode(CallBack,NeedExit=NeedExit)