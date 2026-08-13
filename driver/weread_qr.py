"""
微信读书(Weread)扫码登录驱动

通过微信读书 Web API 实现扫码登录流程：
1. 获取登录 UID
2. 生成二维码
3. 轮询扫码状态
4. 登录成功后提取并保存 Cookie

参考: https://github.com/nasonliu/papers3-weread
"""

import os
import time
import json
import base64
from io import BytesIO
from threading import Lock, Timer
from typing import Optional, Dict, Any

import requests

from core.print import print_info, print_success, print_error, print_warning

WEREAD_BASE = "https://weread.qq.com"
WEREAD_API = "https://i.weread.qq.com"
QR_IMAGE_PATH = "static/weread_qrcode.png"


class WereadQRLogin:
    """微信读书扫码登录管理器（单例模式）"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._uid: str = ""
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

        self._logged_in = False
        self._login_result: Dict[str, Any] = {}
        self._qr_code_path = QR_IMAGE_PATH
        self._has_qr = False

        # 用于轮询的定时器
        self._poll_timer: Optional[Timer] = None
        self._poll_interval = 2  # 轮询间隔（秒）
        self._poll_timeout = 300  # 最大轮询时间（秒）
        self._poll_start_time: float = 0

        # 确保目录存在
        os.makedirs(os.path.dirname(self._qr_code_path), exist_ok=True)

    # ---------- 对外接口 ----------

    def GetCode(self, CallBack=None) -> Optional[str]:
        """
        获取登录二维码
        返回二维码图片 URL 或 base64 数据
        """
        self._reset()

        # 第一步: 获取登录 UID
        uid = self._get_login_uid()
        if not uid:
            print_error("Weread QR: 获取登录 UID 失败")
            return None

        self._uid = uid
        print_info(f"Weread QR: 获取到 UID = {uid}")

        # 第二步: 生成二维码图片
        qr_url = self._generate_qr_image(uid)
        if not qr_url:
            return None

        self._has_qr = True

        # 第三步: 启动轮询
        if CallBack:
            self._start_polling(CallBack)

        return qr_url

    def QrStatus(self) -> Dict[str, Any]:
        """
        返回二维码/登录状态
        返回格式: { "login_status": bool, "code_url": str, "msg": str, "data": dict }
        """
        if not self._uid:
            return {"login_status": False, "code_url": "", "msg": "未开始获取二维码", "data": {}}

        if self._logged_in:
            return {
                "login_status": True,
                "code_url": self._qr_code_path,
                "msg": "登录成功",
                "data": self._login_result,
            }

        # 检查是否有二维码图片
        if not self._has_qr:
            return {"login_status": False, "code_url": "", "msg": "二维码获取中...", "data": {}}

        # 检查是否超时
        if self._poll_start_time and (time.time() - self._poll_start_time > self._poll_timeout):
            msg = "二维码已过期，请重新获取"
            print_warning(f"Weread QR: {msg}")
            return {"login_status": False, "code_url": self._qr_code_path, "msg": msg, "data": {}}

        return {
            "login_status": False,
            "code_url": self._qr_code_path,
            "msg": "等待扫码...",
            "data": {},
        }

    def GetHasCode(self) -> bool:
        """二维码图片文件是否存在"""
        return os.path.exists(self._qr_code_path)

    def HasLogin(self) -> bool:
        """是否已登录成功"""
        return self._logged_in

    def GetLoginResult(self) -> Dict[str, Any]:
        """获取登录结果（Cookie 等）"""
        return self._login_result if self._logged_in else {}

    async def Close(self):
        """关闭登录流程并清理"""
        self._stop_polling()
        # 清理二维码图片
        if os.path.exists(self._qr_code_path):
            try:
                os.remove(self._qr_code_path)
            except Exception:
                pass
        return self._login_result if self._logged_in else {}

    # ---------- 内部方法 ----------

    def _reset(self):
        """重置登录状态"""
        self._uid = ""
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        self._logged_in = False
        self._login_result = {}
        self._has_qr = False
        self._poll_start_time = 0
        self._stop_polling()

    def _get_login_uid(self) -> Optional[str]:
        """
        获取微信读书登录 UID
        GET https://weread.qq.com/api/auth/getLoginUid
        """
        try:
            url = f"{WEREAD_BASE}/api/auth/getLoginUid"
            resp = self._session.get(url, timeout=15)
            if resp.status_code != 200:
                print_error(f"Weread QR: getLoginUid 返回 {resp.status_code}")
                return None

            data = resp.json()
            uid = data.get("uid") or data.get("data", {}).get("uid")
            return str(uid) if uid else None
        except requests.exceptions.Timeout:
            print_error("Weread QR: getLoginUid 超时")
            return None
        except Exception as e:
            print_error(f"Weread QR: getLoginUid 异常: {e}")
            return None

    def _generate_qr_image(self, uid: str) -> Optional[str]:
        """
        根据 UID 生成微信读书登录二维码图片
        使用 qrcode 库生成 PNG 图片
        """
        confirm_url = f"{WEREAD_BASE}/web/confirm?uid={uid}"

        try:
            import qrcode
            from qrcode.image.styledpil import StyledPilImage

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(confirm_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            img.save(self._qr_code_path, format="PNG")
            print_success(f"Weread QR: 二维码已保存到 {self._qr_code_path}")

            return self._qr_code_path
        except ImportError:
            # 没有 qrcode 库时，使用在线服务生成
            print_warning("Weread QR: qrcode 库未安装，使用在线服务生成")
            qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={requests.utils.quote(confirm_url)}"
            return qr_api
        except Exception as e:
            print_error(f"Weread QR: 生成二维码失败: {e}")
            return None

    def _start_polling(self, CallBack):
        """启动轮询定时器"""
        self._poll_start_time = time.time()
        self._poll_once(CallBack)

    def _poll_once(self, CallBack):
        """单次轮询登录状态"""
        try:
            result = self._check_login_status()
        except Exception as e:
            print_error(f"Weread QR: 轮询异常: {e}")
            result = {"succeed": False, "error": str(e)}

        if result.get("succeed"):
            # 登录成功
            self._logged_in = True
            self._login_result = result
            print_success(f"Weread QR: 登录成功! VID = {result.get('vid', '?')}")

            # 保存完整的 Cookie 信息
            result["cookies"] = self._build_cookie_dict()

            if CallBack:
                self._save_cookies_to_lic(result)

            # 通知回调
            if CallBack:
                try:
                    CallBack(result)
                except Exception as e:
                    print_error(f"Weread QR: CallBack 异常: {e}")

            return

        # 检查超时
        if time.time() - self._poll_start_time > self._poll_timeout:
            print_warning("Weread QR: 扫码登录超时")
            return

        # 继续轮询
        self._poll_timer = Timer(self._poll_interval, self._poll_once, args=[CallBack])
        self._poll_timer.daemon = True
        self._poll_timer.start()

    def _stop_polling(self):
        """停止轮询"""
        if self._poll_timer:
            self._poll_timer.cancel()
            self._poll_timer = None

    def _check_login_status(self) -> Dict[str, Any]:
        """
        检查登录状态
        GET https://weread.qq.com/api/auth/getLoginInfo?uid={uid}&otp=
        
        返回示例:
        - 等待扫码: {"succeed": false, "logicCode": 0, ...}
        - 已扫码待确认: {"succeed": false, "logicCode": 1, ...}
        - 登录成功: {"succeed": true, "vid": "xxx", "accessToken": "xxx", ...}
        - 超时: {"succeed": false, "logicCode": "LOGIN_TIMEOUT", ...}
        - 需要验证码: {"succeed": false, "logicCode": "NEED_OTP", ...}
        """
        try:
            url = f"{WEREAD_BASE}/api/auth/getLoginInfo"
            params = {"uid": self._uid, "otp": ""}
            resp = self._session.get(url, params=params, timeout=15)

            if resp.status_code != 200:
                return {"succeed": False, "error": f"HTTP {resp.status_code}"}

            data = resp.json()

            # 检查是否成功
            succeed = data.get("succeed") or data.get("data", {}).get("succeed")
            logic_code = data.get("logicCode", "")

            if succeed:
                # 提取登录信息
                vid = (
                    data.get("webLoginVid")
                    or data.get("vid")
                    or data.get("userVid")
                    or data.get("data", {}).get("userVid", "")
                )
                access_token = data.get("accessToken", "")
                
                # wr_skey 通常在 Set-Cookie 中
                # 如果响应体中没有，从 session cookies 中获取
                wr_skey = ""
                for cookie in self._session.cookies:
                    if cookie.name == "wr_skey":
                        wr_skey = cookie.value
                        break

                # 备用: 使用 accessToken
                if not wr_skey:
                    wr_skey = access_token

                return {
                    "succeed": True,
                    "vid": str(vid) if vid else "",
                    "accessToken": access_token,
                    "wr_skey": wr_skey,
                    "loginInfo": data,
                }

            # 未登录的各种状态
            if logic_code == "NEED_OTP":
                print_warning("Weread QR: 需要验证码，当前暂不支持 OTP 验证")
                return {"succeed": False, "logicCode": logic_code, "need_otp": True}
            elif logic_code == "LOGIN_TIMEOUT":
                print_warning("Weread QR: 登录超时，二维码已失效")
                return {"succeed": False, "logicCode": "LOGIN_TIMEOUT", "timeout": True}

            # 正常等待中
            return {"succeed": False, "logicCode": logic_code}

        except requests.exceptions.Timeout:
            return {"succeed": False, "error": "请求超时"}
        except Exception as e:
            return {"succeed": False, "error": str(e)}

    def _build_cookie_dict(self) -> Dict[str, str]:
        """从 session 构建 Cookie 字典"""
        cookies = {}
        for cookie in self._session.cookies:
            cookies[cookie.name] = cookie.value
        return cookies

    def _save_cookies_to_lic(self, result: Dict[str, Any]):
        """将登录 Cookie 保存到 data/wx.lic"""
        try:
            cookies = result.get("cookies", {})
            vid = result.get("vid", "")

            # 构造完整的 Cookie 字符串
            cookie_parts = []
            for name, value in cookies.items():
                cookie_parts.append(f"{name}={value}")
            cookie_str = "; ".join(cookie_parts)

            if not cookie_str:
                print_error("Weread QR: Cookie 为空，无法保存")
                return

            # 保存到 data/wx.lic
            from core.config import Config

            lic_path = "./data/wx.lic"
            os.makedirs(os.path.dirname(lic_path), exist_ok=True)
            if not os.path.exists(lic_path):
                with open(lic_path, "w") as f:
                    f.write("{}")

            cfg = Config(lic_path)
            weread_data = cfg.get("weread_data", {})
            if isinstance(weread_data, str):
                try:
                    weread_data = json.loads(weread_data)
                except Exception:
                    weread_data = {}

            weread_data["cookie"] = cookie_str
            weread_data["vid"] = str(vid)
            # 保留原有 name（如果有的话）
            if "name" not in weread_data:
                weread_data["name"] = ""

            cfg.set("weread_data", weread_data)
            cfg.save_config()
            cfg.reload()
            print_success(f"Weread QR: Cookie 已保存到 data/wx.lic (VID={vid})")

        except Exception as e:
            print_error(f"Weread QR: 保存 Cookie 失败: {e}")


# ---- 模块级实例 ----
WEREAD_QR_LOGIN = WereadQRLogin()
