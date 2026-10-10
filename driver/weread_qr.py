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
            "Origin": "https://weread.qq.com",
            "Referer": "https://weread.qq.com/",
        })

        self._logged_in = False
        self._login_result: Dict[str, Any] = {}
        self._login_error: str = ""
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

        # 登录成功但 Cookie 验证失败
        if self._login_error:
            return {
                "login_status": False,
                "code_url": self._qr_code_path,
                "msg": self._login_error,
                "data": {"logicCode": "COOKIE_INVALID"},
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
            "Origin": "https://weread.qq.com",
            "Referer": "https://weread.qq.com/",
        })
        self._logged_in = False
        self._login_result = {}
        self._login_error = ""
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
            resp = self._session.get(url, timeout=20)
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
            # 没有 qrcode 库时，不再静默 fallback 到 qrserver.com 在线服务
            # （国内网络无法访问，会导致二维码空白），直接返回 None 报错，
            # 由 API 层向前端返回明确错误提示。
            print_error(
                "Weread QR: 缺少 qrcode 库，无法本地生成二维码。"
                "请执行 pip install qrcode pillow 后重试"
            )
            return None
        except Exception as e:
            print_error(f"Weread QR: 生成二维码失败: {e}")
            return None

    def _start_polling(self, CallBack):
        """
        启动轮询定时器

        注意：绝不能同步调用 _poll_once！getLoginInfo 是长轮询接口，
        最长可挂起 timeout(70s)。若同步执行，GetCode() 会被阻塞数十秒，
        二维码图片虽然已生成，但前端拿不到 URL，一直停在"正在获取二维码..."。
        因此首次轮询必须延时到后台线程启动，让 GetCode() 立即返回。
        """
        self._poll_start_time = time.time()
        self._poll_timer = Timer(0.5, self._poll_once, args=[CallBack])
        self._poll_timer.daemon = True
        self._poll_timer.start()

    def _poll_once(self, CallBack):
        """单次轮询登录状态"""
        try:
            result = self._check_login_status()
        except Exception as e:
            print_error(f"Weread QR: 轮询异常: {e}")
            result = {"succeed": False, "error": str(e)}

        if result.get("succeed"):
            # 登录成功，先构建完整 Cookie 并验证有效性
            result["cookies"] = self._build_cookie_dict()

            # 兜底：确保 wr_vid 存在
            vid = result.get("vid", "")
            if vid and not result["cookies"].get("wr_vid"):
                result["cookies"]["wr_vid"] = str(vid)

            # 多候选组合验证 + renewal 续期（v5）：
            # 微信读书新版扫码登录成功后，Set-Cookie 下发的 wr_skey 是 8 字符
            # 短值（= accessToken），常被服务端以 -2012「登录超时」拒绝；真正的
            # 长令牌是 refreshToken（= wr_rt 的 URL 解码值）。浏览器登录后还会
            # 调用 /web/login/renewal 续期接口，用 wr_rt 换新的有效 wr_skey。
            # 因此对每个候选：先直接验证，失败则先调 renewal 续期（携带含
            # wr_rt 的 Cookie，服务端通过 Set-Cookie 下发新 wr_skey）再验证；
            # 取第一个通过者，全部失败则重试（最多 3 次）。
            verified = False
            best_cookies = result["cookies"]
            for attempt in range(3):
                candidates = self._build_cookie_candidates(result)
                for cand in candidates:
                    if self._verify_cookies(cand, vid):
                        best_cookies = cand
                        verified = True
                        break
                    # 直接验证失败：调用续期接口换新 wr_skey 后再验证
                    # （renewal 依赖 wr_rt，无 wr_rt 的组合续期无意义，跳过）
                    if cand.get("wr_rt"):
                        renewed = self._renew_cookie(cand)
                        if renewed and self._verify_cookies(renewed, vid):
                            best_cookies = renewed
                            verified = True
                            break
                if verified:
                    break
                if attempt < 2:
                    print_warning(f"Weread QR: Cookie 验证未通过，第 {attempt + 1} 次重试...")
                    time.sleep(2)

            if not verified:
                print_error(
                    "Weread QR: 登录成功但 Cookie 验证失败（登录超时/已过期），"
                    "请重新扫码获取有效 Cookie"
                )
                self._login_error = "登录成功但 Cookie 验证失败（登录超时/已过期），请重新扫码"
                return

            # 验证通过的组合作为最终 Cookie
            result["cookies"] = best_cookies
            if best_cookies.get("wr_skey"):
                result["wr_skey"] = best_cookies["wr_skey"]

            # 验证通过才算真正登录成功
            self._logged_in = True
            self._login_result = result
            print_success(f"Weread QR: 登录成功! VID = {result.get('vid', '?')}")

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
            # 微信读书 getLoginInfo 长轮询：响应可能挂起较久，官方实现用 70s
            resp = self._session.get(url, params=params, timeout=70)

            if resp.status_code != 200:
                return {"succeed": False, "error": f"HTTP {resp.status_code}"}

            data = resp.json()

            # 官方实现先归一化嵌套结构：data = r.get("data", r)
            # 部分环境下登录成功信息在顶层，部分在 data 子层
            inner = data.get("data") or {}

            # 检查是否成功
            succeed = data.get("succeed") or inner.get("succeed")
            logic_code = data.get("logicCode", "")

            if succeed:
                # ---- 诊断：打印成功响应结构（脱敏，仅显示字段名与值长度）----
                # 用于排查「登录成功但 wr_skey 提取/验证失败」问题：
                # accessToken 字段的真实位置/命名可能与假设不同，需以实际响应为准。
                try:
                    def _diag_mask(v):
                        if isinstance(v, str) and len(v) > 8:
                            return f"str(len={len(v)}) {v[:6]}...{v[-4:]}"
                        return v

                    top_diag = {k: _diag_mask(v) for k, v in data.items()}
                    print_info(
                        "Weread QR: getLoginInfo 成功响应(顶层) = "
                        + json.dumps(top_diag, ensure_ascii=False, default=str)
                    )
                    if inner:
                        inner_diag = {k: _diag_mask(v) for k, v in inner.items()}
                        print_info(
                            "Weread QR: getLoginInfo 成功响应(data子层) = "
                            + json.dumps(inner_diag, ensure_ascii=False, default=str)
                        )
                    jar_diag = [
                        f"{c.name}="
                        + (f"str(len={len(c.value)}) {c.value[:6]}..." if c.value else "(empty)")
                        for c in self._session.cookies
                    ]
                    print_info("Weread QR: session cookie jar = " + ", ".join(jar_diag))
                except Exception as _diag_err:
                    print_warning(f"Weread QR: 诊断日志输出异常: {_diag_err}")

                # 提取登录信息（顶层与 data 子层都取，官方实现同款字段）
                vid = (
                    data.get("webLoginVid")
                    or data.get("vid")
                    or data.get("userVid")
                    or inner.get("webLoginVid")
                    or inner.get("vid")
                    or inner.get("userVid")
                    or inner.get("user_vid")
                    or ""
                )
                # accessToken 提取：兼容多层嵌套与多种字段名
                # （部分环境下令牌在 data 子层，或使用 access_token / token 命名）
                access_token = (
                    data.get("accessToken")
                    or data.get("access_token")
                    or data.get("token")
                    or inner.get("accessToken")
                    or inner.get("access_token")
                    or inner.get("token")
                    or (inner.get("data") or {}).get("accessToken")
                    or ""
                )
                # refreshToken 提取（微信读书新版：这是真正的长令牌，对应
                # cookie wr_rt 的 URL 解码值，格式形如 web@xxxx；而 accessToken
                # 只是 8 字符短值，被 Set-Cookie 写入 wr_skey 后常被服务端
                # 以 -2012「登录超时」拒绝，需要用 refreshToken 兜底/组合）
                refresh_token = (
                    data.get("refreshToken")
                    or data.get("refresh_token")
                    or inner.get("refreshToken")
                    or inner.get("refresh_token")
                    or ""
                )

                # wr_skey 的获取优先级（v4，基于实测迭代修正）：
                # 1) Set-Cookie 下发的 wr_skey（requests 已处理全部 Set-Cookie 头）
                #    是服务器真正下发的登录令牌，与浏览器行为一致，优先采用；
                #    但短占位值（<20 字符，如 'vhjuyBcI'）不可信，视为缺失。
                # 2) JSON 中已知字段名（accessToken/token/wr_skey/skey/ticket 等，
                #    顶层与 data 子层都查）——兼容部分环境仅通过 JSON 下发令牌。
                #    注意：v3 只查 accessToken 系列字段，从未查过响应里是否直接
                #    存在 wr_skey / skey / ticket 字段，此处补全。
                # 3) 全量自动探测：扫描整个响应与 cookie jar，挑选"最像
                #    wr_skey"的长字符串候选。候选最终会经过 _verify_cookies
                #    真实校验，选错只会验证失败，不会保存错误 Cookie，安全。
                wr_skey = ""
                for cookie in self._session.cookies:
                    if cookie.name == "wr_skey":
                        wr_skey = cookie.value or ""
                        break

                def _tok_short(v):
                    return not v or len(str(v)) < 20

                if _tok_short(wr_skey):
                    # 2) 已知字段名扩展提取
                    for f in (
                        "accessToken", "access_token", "token",
                        "wr_skey", "skey", "sessionKey", "session_key",
                        "authToken", "auth_token", "ticket",
                    ):
                        cand = (
                            data.get(f)
                            or inner.get(f)
                            or (inner.get("data") or {}).get(f)
                            or ""
                        )
                        if cand and not _tok_short(cand):
                            wr_skey = str(cand)
                            break

                if _tok_short(wr_skey):
                    # 3) 全量自动探测兜底
                    candidates = []

                    def _collect(obj, path=""):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                _collect(v, f"{path}.{k}" if path else str(k))
                        elif isinstance(obj, str) and len(obj) >= 20:
                            candidates.append((path, obj))
                        elif isinstance(obj, (list, tuple)):
                            for i, v in enumerate(obj):
                                _collect(v, f"{path}[{i}]")

                    _collect(data)
                    for cookie in self._session.cookies:
                        if cookie.value and len(cookie.value) >= 20:
                            candidates.append((f"cookie:{cookie.name}", cookie.value))

                    if candidates:
                        def _score(item):
                            path, val = item
                            low = path.lower()
                            s = 0
                            for kw in ("skey", "token", "auth", "ticket", "key"):
                                if kw in low:
                                    s += 1
                            return (s, len(val))

                        candidates.sort(key=_score, reverse=True)
                        best_path, best_val = candidates[0]
                        print_warning(
                            "Weread QR: 已知令牌字段均缺失，自动探测候选: "
                            f"path={best_path} len={len(best_val)} "
                            f"(共 {len(candidates)} 个候选)"
                        )
                        wr_skey = best_val

                # 注意：这里不再把探测到的 wr_skey 写回 session jar！
                # 诊断脚本 scripts/weread_scan_diag.py 实测确认（可登录成功）：
                # Set-Cookie 下发的原始 wr_skey（即使是 8 字符短值）就是有效令牌，
                # 无需用 refreshToken 覆盖。探测值仅作为候选交给
                # _build_cookie_candidates 的真实接口校验（raw 原始 jar 组合恒排
                # 第一），不污染后续保存的 Cookie。

                # 官方实现要求 vid 和有效 token 都存在才算登录成功
                vid_str = str(vid) if vid else ""
                if not vid_str or not wr_skey:
                    print_warning(
                        "Weread QR: 登录成功但缺少 vid 或有效 wr_skey "
                        f"(vid={'有' if vid_str else '无'}, wr_skey={'有' if wr_skey else '无'})"
                    )
                    return {
                        "succeed": False,
                        "logicCode": "INCOMPLETE_LOGIN",
                        "msg": "扫码成功但未获取到有效登录令牌，请重试",
                    }

                return {
                    "succeed": True,
                    "vid": vid_str,
                    "accessToken": access_token,
                    "refreshToken": refresh_token,
                    "wr_skey": wr_skey,
                    "loginInfo": data,
                }

            # 未登录的各种状态
            if logic_code == "NEED_OTP":
                print_warning("Weread QR: 需要验证码，当前暂不支持 OTP 验证")
                return {"succeed": False, "logicCode": logic_code, "need_otp": True}

            # 注意：微信读书 getLoginInfo 在“等待扫码”阶段就返回
            # logicCode == "LOGIN_TIMEOUT"，这是正常的长轮询状态，必须继续轮询，
            # 不能当作二维码失效（参考 papers3-weread 官方实现）。
            # 只有整体轮询超过 self._poll_timeout 才真正过期。
            if logic_code == "LOGIN_TIMEOUT":
                return {"succeed": False, "logicCode": "WAITING"}

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

    def _build_cookie_candidates(self, result: Dict[str, Any]) -> list:
        """构造多种登录 Cookie 组合，供真实接口验证逐个尝试。

        微信读书新版扫码登录成功后，服务器 Set-Cookie 下发的 wr_skey 是
        8 字符短值（= accessToken），常被服务端以 -2012「登录超时」拒绝；
        真正的长令牌是 refreshToken（格式 web@xxxx，对应 wr_rt 的 URL
        解码值，wr_rt = quote(refreshToken)）。但不同环境下服务端可能只认
        长值 wr_skey，或只认未编码/已编码的 wr_rt，因此枚举以下组合：
          A. wr_skey=短值 + wr_rt=已编码     （原始 Set-Cookie）
          B. wr_skey=短值 + wr_rt=未编码
          C. wr_skey=refreshToken + wr_rt=已编码
          D. wr_skey=refreshToken + wr_rt=未编码
          E. 仅 wr_rt=已编码
          F. 仅 wr_rt=未编码
          G. 仅 wr_skey=refreshToken
        另把 v4 自动探测得到的 wr_skey 候选也纳入，重复组合去重。
        """
        from urllib.parse import quote

        base = dict(result.get("cookies") or {})
        vid = result.get("vid", "")
        if vid and not base.get("wr_vid"):
            base["wr_vid"] = str(vid)

        short_skey = str(result.get("accessToken") or base.get("wr_skey") or "")
        rt = str(result.get("refreshToken") or "")
        rt_encoded = quote(rt, safe="") if rt else ""
        base_no_tokens = {k: v for k, v in base.items() if k not in ("wr_skey", "wr_rt")}

        # wr_skey 候选：短值(accessToken) / refreshToken / 自动探测值
        skey_cands = [short_skey, rt, str(result.get("wr_skey") or "")]
        skey_cands = list(dict.fromkeys(s for s in skey_cands if s))
        # wr_rt 候选：已编码 / 未编码（refreshToken）
        rt_cands = [rt_encoded, rt, str(base.get("wr_rt") or "")]
        rt_cands = list(dict.fromkeys(r for r in rt_cands if r))

        variants = []
        for sk in skey_cands:
            v = {"wr_skey": sk}
            variants.append(v)  # 仅 wr_skey，无 wr_rt
            for rk in rt_cands:
                variants.append({"wr_skey": sk, "wr_rt": rk})
        for rk in rt_cands:
            variants.append({"wr_rt": rk})  # 仅 wr_rt，无 wr_skey

        seen, out = set(), []
        for v in variants:
            cand = dict(base_no_tokens)
            for k, val in v.items():
                if val:
                    cand[k] = val
            key = tuple(sorted((k, cand[k]) for k in cand))
            if key not in seen:
                seen.add(key)
                out.append(cand)

        # 原始 jar 组合始终放第一位（最保守）
        raw = dict(base)
        raw_key = tuple(sorted((k, raw[k]) for k in raw))
        if raw_key not in seen:
            out.insert(0, raw)
        return out

    def _renew_cookie(self, cookies: Dict[str, str]) -> Optional[Dict[str, str]]:
        """调用微信读书续期接口 /web/login/renewal，用 wr_rt 换新的 wr_skey。

        对齐 scripts/weread_scan_diag.py 的激活路径（实测可续期成功）：
        **必须把登录 Cookie 注入 requests.Session 的 cookie jar（domain=
        weread.qq.com）再请求**，模拟浏览器登录后的 session，否则服务端把请求
        当游客处理，返回 -2013「鉴权失败」（生产代码此前一直 -2013 即由此导致；
        诊断脚本注释：'关键修复：注入 getLoginInfo 下发的登录 cookie，否则服务端
        把请求当游客处理，永不补发完整 cookie（此前 -2013 也由此导致）'）。

        body 为 {"rq": "%2Fweb%2Fbook%2Fread", "ql": true}（带 ql 的变体）。
        成功返回更新后的 Cookie dict（含新 wr_skey），失败返回 None。
        """
        try:
            s = requests.Session()
            s.headers.update({
                "User-Agent": self._session.headers.get("User-Agent", ""),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Origin": "https://weread.qq.com",
                "Referer": "https://weread.qq.com/",
                "Content-Type": "application/json",
            })
            # 关键：注入登录 Cookie 到 session jar（diagnose 脚本实测必要）
            for k, v in cookies.items():
                s.cookies.set(k, v, domain="weread.qq.com", path="/")

            body = {"rq": "%2Fweb%2Fbook%2Fread", "ql": True}
            resp = s.post(
                f"{WEREAD_BASE}/web/login/renewal",
                data=json.dumps(body, separators=(",", ":")),
                timeout=20,
            )
            # requests 已把 Set-Cookie 自动并入 session jar，从 jar 读取更新值
            # 注意：renewal 下发的 wr_skey 可能仍是 8 字符短值（wr_skey 本身就是
            # 短效令牌，靠 renewal 持续换新），不能以长度 <20 判失败，
            # 交给后续 _verify_cookies 真实校验把关。
            updated = dict(cookies)
            new_skey = ""
            for c in s.cookies:
                if c.name == "wr_skey" and c.value:
                    new_skey = c.value
                    updated["wr_skey"] = c.value
                elif c.name == "wr_vid" and c.value:
                    updated["wr_vid"] = c.value
                elif c.name == "wr_rt" and c.value:
                    updated["wr_rt"] = c.value

            # 兜底：响应 JSON body 里若直接带新 wr_skey 也采纳
            if not new_skey:
                try:
                    j = resp.json()
                    if isinstance(j, dict):
                        for f in ("wr_skey", "skey", "token"):
                            v = j.get(f)
                            if isinstance(v, str) and v:
                                new_skey = v
                                updated["wr_skey"] = v
                                break
                except Exception:
                    pass

            if new_skey:
                print_success(
                    f"Weread QR: renewal 续期成功，新 wr_skey len={len(new_skey)}"
                )
                return updated
            print_warning(
                f"Weread QR: renewal 未获取到新 wr_skey "
                f"(status={resp.status_code} body={resp.text[:150]!r} "
                f"Set-Cookie={resp.headers.get('Set-Cookie', '')[:150]!r})"
            )
            return None
        except Exception as e:
            print_warning(f"Weread QR: renewal 调用异常: {e}")
            return None

    def _verify_cookies(self, cookies: Dict[str, str], vid: str) -> bool:
        """
        用真实接口验证 Cookie 是否有效。

        对齐 scripts/weread_scan_diag.py（实测可登录成功）的验证方式：
          1) 优先 weread 主站 /web/shelf/sync：userVid 必须传空字符串！
             参考 steptian/weread-mp：userVid 非空反而会触发 -2012「登录超时」；
          2) 再用 /web/mp/articles 兜底（纯 Cookie 即可、无 x-wr-ticket）。
        请求头需带 Origin/Referer（浏览器行为），返回 errCode == -2012 表示
        登录超时 / Cookie 无效。
        """
        try:
            # 构造完整 Cookie 字符串，确保包含 wr_vid / wr_skey / wr_rt
            cookie_parts = [f"{k}={v}" for k, v in cookies.items()]
            cookie_str = "; ".join(cookie_parts)
            headers = {
                "Cookie": cookie_str,
                "User-Agent": self._session.headers.get("User-Agent", ""),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Origin": "https://weread.qq.com",
                "Referer": "https://weread.qq.com/",
            }
            # 1) weread 主站书架接口（userVid='' 空字符串是关键：
            #    非空反而触发 -2012，参考 scripts/weread_scan_diag.py 实测）
            try:
                r = requests.get(
                    f"{WEREAD_BASE}/web/shelf/sync",
                    params={"userVid": "", "synckey": 0},
                    headers=headers,
                    timeout=20,
                )
                if r.status_code == 200:
                    j = r.json()
                    code = j.get("errCode", j.get("errcode", 0))
                    if not code and (
                        "books" in j or "bookCount" in j or "synckey" in j
                    ):
                        return True
            except Exception:
                pass

            # 2) weread 主站 mp 接口兜底（同样完整请求头）
            try:
                r = requests.get(
                    f"{WEREAD_BASE}/web/mp/articles",
                    params={"bookId": "MP_WXS_3528995129", "offset": 0},
                    headers=headers,
                    timeout=20,
                )
                if r.status_code == 200:
                    j = r.json()
                    code = j.get("errCode", j.get("errcode", 0))
                    if not code and (
                        "reviews" in j or "articles" in j or "synckey" in j or j.get("bookId")
                    ):
                        return True
            except Exception:
                pass

            last_desc = ""
            try:
                last_desc = f"status={r.status_code} body={r.text[:200]!r}"
            except Exception:
                last_desc = "(请求异常，无法取回响应)"
            print_warning(f"Weread QR: Cookie 验证失败 {last_desc}")
            return False
        except Exception as e:
            print_warning(f"Weread QR: Cookie 验证异常: {e}")
            return False

    def _save_cookies_to_lic(self, result: Dict[str, Any]):
        """将登录 Cookie 保存到 data/wx.lic（保存前先验证有效性）"""
        try:
            # 以登录 session 的完整 jar 为基础（含 wr_rt / wr_ql / wr_vid 等
            # Set-Cookie 原始字段），仅用验证通过的 wr_skey / vid 覆盖。
            # 注意：不能用 result["cookies"]（那是验证通过的候选组合，可能缺
            # wr_rt 等字段，实测导致保存后 i 域/web 域请求 401/-2012）。
            cookies = dict(self._build_cookie_dict())
            vid = result.get("vid", "")

            # 兜底：确保 wr_vid 存在
            if vid and not cookies.get("wr_vid"):
                cookies["wr_vid"] = str(vid)
            # 关键：用验证通过的 wr_skey 强制覆盖 jar 中服务器下发的短占位值
            wr_skey = result.get("wr_skey", "")
            if wr_skey:
                cookies["wr_skey"] = wr_skey

            # 构造完整的 Cookie 字符串
            cookie_parts = []
            for name, value in cookies.items():
                cookie_parts.append(f"{name}={value}")
            cookie_str = "; ".join(cookie_parts)

            if not cookie_str:
                print_error("Weread QR: Cookie 为空，无法保存")
                return

            # 先验证 Cookie 有效性，无效则不覆盖已有配置
            if not self._verify_cookies(cookies, vid):
                print_error(
                    "Weread QR: 登录成功但 Cookie 验证失败（登录超时/已过期），"
                    "未保存。请重新扫码获取有效 Cookie"
                )
                self._login_error = (
                    "登录成功但 Cookie 验证失败（登录超时/已过期），未保存，请重新扫码"
                )
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

            # 多账号：迁移旧格式到 accounts 数组，新账号追加到数组末尾
            accounts = weread_data.get("accounts", None)
            if not isinstance(accounts, list):
                # 旧格式迁移：weread_data.cookie 包成 accounts[0]
                if weread_data.get("cookie"):
                    accounts = [{
                        "cookie": weread_data["cookie"],
                        "vid": weread_data.get("vid", ""),
                        "name": weread_data.get("name", ""),
                    }]
                else:
                    accounts = []

            # 如果相同 vid 已存在，更新它（重新扫码刷新 cookie）
            existing_idx = next(
                (i for i, a in enumerate(accounts) if str(a.get("vid", "")) == str(vid)),
                None,
            )
            account_entry = {
                "cookie": cookie_str,
                "vid": str(vid),
                "name": result.get("name", "") or "",
            }
            if existing_idx is not None:
                # 保留原有 name（如果用户改过）
                account_entry["name"] = accounts[existing_idx].get("name", "")
                accounts[existing_idx] = account_entry
            else:
                accounts.append(account_entry)

            # 写回 accounts 数组，清掉旧格式字段
            weread_data["accounts"] = accounts
            for k in ("cookie", "vid", "name", "ticket"):
                weread_data.pop(k, None)

            cfg.set("weread_data", weread_data)
            cfg.save_config()
            cfg.reload()
            print_success(f"Weread QR: Cookie 已保存到 data/wx.lic (VID={vid})，当前共 {len(accounts)} 个账号")

        except Exception as e:
            print_error(f"Weread QR: 保存 Cookie 失败: {e}")


# ---- 模块级实例 ----
WEREAD_QR_LOGIN = WereadQRLogin()
