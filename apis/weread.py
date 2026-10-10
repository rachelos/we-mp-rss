"""
微信读书(Weread)管理 API

提供 Cookie 配置、连接测试、手动采集等功能
"""

import json
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from .base import success_response, error_response
from core.auth import get_current_user_or_ak, get_current_user
from core.config import Config, cfg as app_cfg
from driver.weread_qr import WereadQRLogin

router = APIRouter(prefix="/weread", tags=["微信读书"])


class WereadCookieRequest(BaseModel):
    cookie: Optional[str] = None
    ticket: Optional[str] = None
    vid: Optional[str] = ""
    name: Optional[str] = ""


class WereadConfigRequest(BaseModel):
    """微信读书 Cookie 自动刷新配置（用于定时任务前自动更新 Cookie）"""
    cookie_refresh_url: Optional[str] = ""
    browser_path: Optional[str] = ""
    browser_type: Optional[str] = "chrome"


class WereadCollectRequest(BaseModel):
    mp_id: str
    mp_name: Optional[str] = ""
    faker_id: Optional[str] = ""  # 书籍 bookId，为空则采集全部书架
    max_page: int = 1
    gather_content: bool = True


class WereadMPTestRequest(BaseModel):
    mp_id: Optional[str] = ""


def _get_weread_config() -> Config:
    """获取微信读书配置文件"""
    lic_path = "./data/wx.lic"
    os.makedirs(os.path.dirname(lic_path), exist_ok=True)
    if not os.path.exists(lic_path):
        with open(lic_path, "w") as f:
            f.write("{}")
    return Config(lic_path)


def _load_weread_data() -> dict:
    """加载微信读书数据"""
    cfg = _get_weread_config()
    data = cfg.get("weread_data", {})
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    return data


def _save_weread_data(data: dict):
    """保存微信读书数据"""
    cfg = _get_weread_config()
    cfg.set("weread_data", data)
    cfg.save_config()
    cfg.reload()


def _normalize_accounts(data: dict) -> list:
    """把 weread_data 归一化成 accounts 数组（兼容旧的单账号 cookie 字段）。

    旧版只存 ``weread_data.cookie`` 单个账号；多账号版本存
    ``weread_data.accounts`` 数组。两者可共存，返回的列表始终是
    ``[{cookie, vid, ticket, name}, ...]``。
    """
    accounts = data.get("accounts")
    if isinstance(accounts, list) and accounts:
        return accounts
    # 旧格式迁移：单个 cookie 包成 1 元素数组
    legacy = []
    if data.get("cookie"):
        legacy.append({
            "cookie": data.get("cookie", ""),
            "vid": data.get("vid", ""),
            "ticket": data.get("ticket", ""),
            "name": data.get("name", ""),
        })
    return legacy


def _mask(secret: str, keep: int = 6) -> str:
    """凭据脱敏：只保留开头若干字符，用于在页面展示账号列表"""
    secret = secret or ""
    if len(secret) <= keep:
        return "***" if secret else ""
    return f"{secret[:keep]}***{secret[-4:]}"


def _account_views(data: dict) -> list:
    """构造给前端展示的账号列表（不含完整 Cookie）"""
    views = []
    for idx, acc in enumerate(_normalize_accounts(data), start=1):
        vid = str(acc.get("vid", "") or "")
        views.append({
            "index": idx,
            "vid": vid,
            "name": acc.get("name", "") or f"账号{idx}",
            "cookie_masked": _mask(acc.get("cookie", "")),
            "has_ticket": bool(acc.get("ticket", "")),
            # 主账号（数组第一项）等价于旧版的「当前账号」
            "is_primary": idx == 1,
        })
    return views


@router.get("", summary="获取微信读书配置状态")
async def get_weread_status(current_user=Depends(get_current_user_or_ak)):
    """获取当前微信读书 Cookie 的配置状态"""
    data = _load_weread_data()
    config_cookie = app_cfg.get("weread.cookie", "")
    config_ticket = app_cfg.get("weread.ticket", "")
    config_vid = app_cfg.get("weread.vid", "")
    accounts = _normalize_accounts(data)
    # 主账号（第一项）作为兼容字段回显；未迁移的旧格式由 _normalize_accounts 包装
    primary = accounts[0] if accounts else {}
    cookie = config_cookie or primary.get("cookie", "") or data.get("cookie", "")
    ticket = config_ticket or primary.get("ticket", "") or data.get("ticket", "")
    vid = config_vid or primary.get("vid", "") or data.get("vid", "")
    name = primary.get("name", "") or data.get("name", "")
    gather_model = app_cfg.get("gather.model", "web") or "web"

    # 判断是否已配置
    has_cookie = bool(cookie and vid)

    return success_response({
        "configured": has_cookie,
        # 多账号：账号数量 + 脱敏列表（前端据此渲染「第N个微信」）
        "account_count": len(accounts),
        "accounts": _account_views(data),
        "cookie_masked": cookie[:20] + "..." if cookie else "",
        "ticket_masked": ticket[:12] + "..." if ticket else "",
        "cookie": cookie,          # 完整 Cookie（供管理页回显，自托管单用户场景）
        "ticket": ticket,          # 完整 x-wr-ticket（如有）
        "has_cookie": bool(cookie),
        "has_ticket": bool(ticket),
        "mp_configured": bool(cookie),
        "gather_model": gather_model,
        "managed_by_config": bool(config_cookie or config_ticket or config_vid),
        "cookie_managed_by_config": bool(config_cookie),
        "ticket_managed_by_config": bool(config_ticket),
        "vid": vid,
        "name": name,
        "cookie_refresh_url": data.get("cookie_refresh_url", ""),
        "browser_path": data.get("browser_path", ""),
        "browser_type": data.get("browser_type", "chrome"),
    })


@router.post("/cookie", summary="保存微信读书 Cookie")
async def save_weread_cookie(
    req: WereadCookieRequest,
    current_user=Depends(get_current_user_or_ak),
):
    """
    保存微信读书 Cookie 和可选的公众号文章列表 ticket
    
    所需 Cookie: wr_vid, wr_skey, wr_gid, wr_fp 等
    可以从浏览器 weread.qq.com 的请求中获取
    """
    data = _load_weread_data()
    config_cookie = app_cfg.get("weread.cookie", "")
    config_ticket = app_cfg.get("weread.ticket", "")
    if config_cookie and req.cookie is not None:
        return error_response(409, "Cookie 由 config.yaml 或环境变量管理，不能在页面覆盖")
    if config_ticket and req.ticket is not None:
        return error_response(409, "x-wr-ticket 由 config.yaml 或环境变量管理，不能在页面覆盖")

    accounts = _normalize_accounts(data)
    # 未传 cookie 时沿用主账号（保持旧行为：只改 ticket/name 不动 cookie）
    fallback_cookie = accounts[0].get("cookie", "") if accounts else data.get("cookie", "")
    cookie_str = config_cookie or (req.cookie.strip() if req.cookie else fallback_cookie)
    if not cookie_str:
        return error_response(400, "Cookie 不能为空")

    # 提取 vid
    vid = (req.vid or "").strip()
    if not vid:
        for item in cookie_str.split(";"):
            item = item.strip()
            if item.startswith("wr_vid="):
                vid = item.replace("wr_vid=", "").strip()
                break

    if not vid:
        return error_response(400, "Cookie 中未找到 wr_vid，请检查 Cookie 格式")

    ticket_str = req.ticket.strip() if req.ticket is not None else None
    name_str = (req.name or "").strip()

    if config_cookie:
        # 凭据由 config.yaml/环境变量托管：不在 wx.lic 里建账号，只记 ticket/name
        if ticket_str is not None:
            data["ticket"] = ticket_str
        if name_str:
            data["name"] = name_str
        _save_weread_data(data)
        return success_response({
            "vid": vid,
            "name": data.get("name", ""),
            "account_count": len(accounts),
        }, "Cookie 保存成功（凭据由部署配置托管）")

    # 写入 accounts 数组：同 vid 视为该账号刷新 Cookie，否则追加为新账号。
    # 与 driver/weread_qr.py 的 _save_cookies_to_lic 保持同一套去重口径。
    new_entry = {
        "cookie": cookie_str,
        "vid": vid,
        "ticket": ticket_str if ticket_str is not None else "",
        "name": name_str,
    }
    matched = None
    for acc in accounts:
        if str(acc.get("vid", "")) == vid:
            matched = acc
            break
    if matched is not None:
        # 保留用户改过的 name（未显式填写时不清空）
        new_entry["name"] = name_str or matched.get("name", "")
        if ticket_str is None:
            new_entry["ticket"] = matched.get("ticket", "")
        accs = accounts
        accs[accs.index(matched)] = new_entry
        action = "updated"
    else:
        accs = accounts + [new_entry]
        action = "added"

    data["accounts"] = accs
    # 旧格式字段清空，避免两处各存一份 cookie 后互相覆盖
    for key in ("cookie", "vid", "name", "ticket"):
        data.pop(key, None)
    _save_weread_data(data)

    return success_response({
        "vid": vid,
        "name": new_entry["name"],
        "action": action,
        "account_count": len(accs),
        "accounts": _account_views(data),
    }, f"Cookie 保存成功，当前共 {len(accs)} 个微信账号")


@router.post("/config", summary="保存微信读书 Cookie 自动刷新配置")
async def save_weread_config(
    req: WereadConfigRequest,
    current_user=Depends(get_current_user_or_ak),
):
    """
    保存 Cookie 自动刷新的浏览器/URL 配置。
    这些不是敏感凭据，由项目内的刷新脚本（core/weread_cookie_refresh.py）
    读取后调用本机 Chrome 打开 URL 提取最新 Cookie。
    """
    data = _load_weread_data()
    data["cookie_refresh_url"] = (req.cookie_refresh_url or "").strip()
    data["browser_path"] = (req.browser_path or "").strip()
    data["browser_type"] = (req.browser_type or "chrome").strip() or "chrome"
    _save_weread_data(data)
    return success_response(message="自动刷新配置已保存")


@router.post("/test", summary="测试微信读书连接")
async def test_weread_connection(current_user=Depends(get_current_user_or_ak)):
    """
    测试微信读书 Cookie 是否有效
    会尝试获取书架数据来验证
    """
    from core.wx.model.weread import MpsWeread

    wx = MpsWeread()
    result = wx.test_auth()

    if result["ok"]:
        return success_response(result, f"连接成功，书架共 {result['book_count']} 本书")
    else:
        return error_response(400, result.get("error", "连接失败"), result)


@router.post("/mp/test", summary="测试微信读书公众号采集连接")
async def test_weread_mp_connection(
    req: WereadMPTestRequest,
    current_user=Depends(get_current_user_or_ak),
):
    """Use an existing MP feed to validate the configured WeRead credentials."""
    from core.db import DB
    from core.models.feed import Feed
    from core.wx.model.weread_mp import MpsWereadMP, WereadMPAPIError

    mp_id = (req.mp_id or "").strip()
    if not mp_id:
        session = DB.get_session()
        try:
            feed = session.query(Feed.id).filter(Feed.id.like("MP_WXS_%")).first()
            mp_id = feed[0] if feed else ""
        finally:
            session.close()
    if not mp_id:
        return error_response(400, "请先导入至少一个 MP_WXS_ 公众号再测试")

    wx = MpsWereadMP()
    wx._load_weread_auth()
    try:
        # 新版微信读书已废弃 /web/mp/articles，用 /api/mp/cover 验证凭据与公众号
        cover = wx._get_mp_cover(mp_id)
        review_id = cover.get("reviewId", "")
        article_count = 1 if review_id else 0
    except WereadMPAPIError as exc:
        return error_response(400, str(exc), {
            "code": exc.code,
            "retriable": exc.retriable,
        })

    return success_response({
        "mp_id": mp_id,
        "mp_name": cover.get("name", ""),
        "latest_title": cover.get("title", ""),
        "article_count": article_count,
    }, "公众号采集凭据有效")


@router.post("/bookshelf", summary="获取书架书籍列表")
async def get_bookshelf(current_user=Depends(get_current_user_or_ak)):
    """
    获取微信读书书架上的所有书籍
    用于选择要采集哪本书的笔记
    """
    from core.wx.model.weread import MpsWeread

    wx = MpsWeread()
    wx._load_weread_auth()

    if not wx._weread_cookies:
        return error_response(400, "请先配置微信读书 Cookie")

    if not wx._weread_vid:
        return error_response(400, "无法从 Cookie 提取 vid")

    books = wx._get_shelf_books()
    if books is None:
        return error_response(500, "获取书架失败，Cookie 可能已过期")

    return success_response({
        "total": len(books),
        "books": books,
    })


def _normalize_weread_mp_id(raw: str) -> str:
    """去掉前端 WEREAD_ 前缀，还原微信读书原始 bookId。

    前端 WereadManagement 以 ``WEREAD_{book_id}`` 作为 mp_id（如
    ``WEREAD_MP_WXS_3012726261``），后端统一规范化为 ``MP_WXS_3012726261``，
    否则 cover 接口与 feeds 表匹配都会失败。
    """
    s = (raw or "").strip()
    if s.startswith("WEREAD_"):
        s = s[len("WEREAD_"):]
    return s


def _ensure_weread_mp_feed(book_id: str, mp_name: str) -> None:
    """公众号文章采集前确保 feeds 表存在对应订阅源（无则自动创建）。

    微信读书书架里采集的公众号（MP_WXS_*）通常并未添加为 WeRSS 订阅源，
    若只把文章写入 articles 表，前端列表 / RSS 里看不到。这里自动补一条
    feed 记录，采集结果才能正常展示。
    """
    from datetime import datetime
    import base64

    from core.db import DB
    from core.models.feed import Feed
    from core.print import print_info

    book_id = (book_id or "").strip()
    if not book_id.startswith("MP_WXS_"):
        return
    session = DB.get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == book_id).first()
        if feed is not None:
            return
        digits = "".join(ch for ch in book_id[len("MP_WXS_"):] if ch.isdigit())
        faker_id = base64.b64encode(digits.encode("utf-8")).decode("utf-8")
        now = datetime.now()
        session.add(Feed(
            id=book_id,
            mp_name=mp_name or book_id,
            status=1,
            sync_time=0,
            update_time=0,
            created_at=now,
            updated_at=now,
            faker_id=faker_id,
        ))
        session.commit()
        print_info(f"已自动创建公众号订阅源: {book_id} ({mp_name})")
    finally:
        session.close()


@router.post("/collect", summary="手动采集微信读书笔记")
async def collect_weread_notes(
    req: WereadCollectRequest,
    current_user=Depends(get_current_user_or_ak),
):
    """
    手动触发微信读书采集（自动分档）

    - 公众号订阅书（bookId 以 MP_WXS_ 开头）→ 采集公众号文章（weread_mp 模式）
    - 普通电子书 → 采集笔记/划线（weread 模式）
    未指定 faker_id 时遍历书架，公众号书自动跳过划线采集。
    """
    if not req.mp_id:
        return error_response(400, "mp_id 不能为空")

    from core.wx.model.weread import MpsWeread
    from core.wx.model.weread_mp import MpsWereadMP, WereadMPAPIError

    # 规范化 WEREAD_ 前缀，保证公众号分支判断与 feeds 匹配一致
    faker_id = _normalize_weread_mp_id(req.faker_id)
    mp_id = _normalize_weread_mp_id(req.mp_id)
    is_mp_article = faker_id.startswith("MP_WXS_") or mp_id.startswith("MP_WXS_")

    wx = MpsWereadMP() if is_mp_article else MpsWeread()
    mode_name = "公众号文章" if is_mp_article else "笔记/划线"
    wx._load_weread_auth()

    if not wx._weread_cookies:
        return error_response(400, "请先配置微信读书 Cookie")

    # 公众号文章模式：确保订阅源存在，采集结果才能在前端/RSS 展示
    if is_mp_article:
        book_id = faker_id if faker_id.startswith("MP_WXS_") else mp_id
        _ensure_weread_mp_feed(book_id, req.mp_name or faker_id)

    articles = []

    def save_callback(data: dict) -> bool:
        """回调：将笔记存入数据库"""
        from core.db import DB

        try:
            art = {
                "id": data.get("id", ""),
                "mp_id": data.get("mp_id", ""),
                "title": data.get("title", ""),
                "url": data.get("url", data.get("link", "")),
                "pic_url": data.get("cover", data.get("pic_url", "")),
                "content": data.get("content", ""),
                "publish_time": data.get("publish_time", data.get("update_time", 0)),
            }
            # 直接使用 DB 添加文章
            DB.add_article(art, check_exist=True)
            articles.append(art)
            return True
        except Exception as e:
            from core.print import print_error
            print_error(f"保存笔记失败: {e}")
            return False

    try:
        wx.get_Articles(
            faker_id=faker_id or None,
            Mps_id=mp_id,
            Mps_title=req.mp_name or faker_id or "微信读书",
            CallBack=save_callback,
            MaxPage=1,
            interval=3,
            Gather_Content=req.gather_content,
        )
    except WereadMPAPIError as exc:
        return error_response(400, f"采集失败: {exc}", {
            "code": exc.code,
            "retriable": exc.retriable,
        })
    except Exception as exc:
        return error_response(500, f"采集异常: {exc}")

    return success_response({
        "collected": len(articles),
        "articles": articles[:20],  # 只返回前20条
    }, f"采集完成，共 {len(articles)} 条{mode_name}")


@router.delete("/cookie", summary="清除微信读书 Cookie")
async def clear_weread_cookie(
    vid: str = "",
    current_user=Depends(get_current_user_or_ak),
):
    """清除已保存的微信读书 Cookie

    - 带 ``vid``：只清除该账号（保留其它账号，可用于下线某个微信号）
    - 不带 ``vid``：清除全部账号（保持旧版行为）
    """
    if any(app_cfg.get(key, "") for key in ("weread.cookie", "weread.ticket", "weread.vid")):
        return error_response(409, "凭据由 config.yaml 或环境变量管理，请在部署配置中清除")

    data = _load_weread_data()
    accounts = _normalize_accounts(data)

    if vid:
        accounts = [a for a in accounts if str(a.get("vid", "")) != vid]
        data["accounts"] = accounts
        for key in ("cookie", "vid", "name", "ticket"):
            data.pop(key, None)
        _save_weread_data(data)
        return success_response(
            {
                "account_count": len(accounts),
                "accounts": _account_views(data),
            },
            f"账号 {vid} 已清除，剩余 {len(accounts)} 个",
        )

    data["accounts"] = []
    data["cookie"] = ""
    data["ticket"] = ""
    data["vid"] = ""
    # 保留 name
    _save_weread_data(data)

    return success_response(
        {"account_count": 0, "accounts": []},
        "全部微信账号的 Cookie 已清除",
    )


# ---- 微信读书扫码授权 API ----

def _weread_qr_callback(result: dict):
    """
    扫码成功后的回调：将 Cookie 保存到 data/wx.lic
    此函数由 driver/weread_qr.py 在登录成功时自动调用
    """
    pass  # 保存逻辑已在 WereadQRLogin._save_cookies_to_lic 中实现


@router.get("/qr/code", summary="获取微信读书登录二维码")
def get_weread_qrcode(current_user=Depends(get_current_user)):
    """
    获取微信读书扫码登录二维码
    返回二维码图片 URL（本地静态路径或外部链接）
    注意：内部有 getLoginUid 网络请求（同步阻塞），必须用普通 def 让
    FastAPI 自动放入线程池执行，否则会阻塞事件循环拖慢所有请求。
    """
    wr_qr = WereadQRLogin()

    def on_login_success(result: dict):
        """登录成功回调"""
        print("Weread QR 登录成功，Cookie 已自动保存")
        _weread_qr_callback(result)

    code_url = wr_qr.GetCode(CallBack=on_login_success)
    if not code_url:
        return error_response(500, "获取二维码失败，请稍后重试")

    # 如果是本地文件路径，转为前端可访问的 /static/ 路径
    if code_url.startswith("static/") or code_url.startswith("./static/"):
        code_url = "/" + code_url.lstrip("./")

    return success_response({"code": code_url, "uid": wr_qr._uid})


@router.get("/qr/image", summary="获取微信读书二维码图片状态")
async def weread_qr_image(current_user=Depends(get_current_user)):
    """检查二维码图片是否存在"""
    wr_qr = WereadQRLogin()
    return success_response(wr_qr.GetHasCode())


@router.get("/qr/status", summary="获取微信读书扫码状态")
async def weread_qr_status(current_user=Depends(get_current_user)):
    """
    轮询微信读书扫码登录状态

    返回:
    - login_status: bool - 是否登录成功
    - code_url: str - 二维码 URL
    - msg: str - 状态消息
    - data: dict - 登录数据（成功后包含 vid, accessToken, cookies 等）
    """
    wr_qr = WereadQRLogin()
    status = wr_qr.QrStatus()
    return success_response(status)


@router.get("/qr/over", summary="微信读书扫码完成")
async def weread_qr_over(current_user=Depends(get_current_user)):
    """
    扫码登录完成后调用，清理状态并返回登录结果
    """
    wr_qr = WereadQRLogin()
    result = await wr_qr.Close()
    return success_response(result)
