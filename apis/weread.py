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
from core.config import Config, cfg as app_cfg
from core.auth import get_current_user_or_ak, get_current_user
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


@router.get("", summary="获取微信读书配置状态")
async def get_weread_status(current_user=Depends(get_current_user_or_ak)):
    """获取当前微信读书 Cookie 的配置状态"""
    data = _load_weread_data()
    config_cookie = app_cfg.get("weread.cookie", "")
    config_ticket = app_cfg.get("weread.ticket", "")
    config_vid = app_cfg.get("weread.vid", "")
    cookie = config_cookie or data.get("cookie", "")
    ticket = config_ticket or data.get("ticket", "")
    vid = config_vid or data.get("vid", "")
    name = data.get("name", "")

    # 判断是否已配置
    has_cookie = bool(cookie and vid)

    return success_response({
        "configured": has_cookie,
        "cookie_masked": cookie[:20] + "..." if cookie else "",
        "ticket_masked": ticket[:12] + "..." if ticket else "",
        "cookie": cookie,          # 完整 Cookie（供管理页回显，自托管单用户场景）
        "ticket": ticket,          # 完整 x-wr-ticket（如有）
        "has_cookie": bool(cookie),
        "has_ticket": bool(ticket),
        "mp_configured": bool(cookie and ticket),
        "managed_by_config": bool(config_cookie or config_ticket or config_vid),
        "cookie_managed_by_config": bool(config_cookie),
        "ticket_managed_by_config": bool(config_ticket),
        "vid": vid,
        "name": name,
        "cookie_refresh_url": data.get("cookie_refresh_url", ""),
        "browser_path": data.get("browser_path", ""),
        "browser_type": data.get("browser_type", "chrome"),
    })


@router.get("/browsers", summary="探测宿主机已安装浏览器（配置页下拉用）")
async def list_weread_browsers(current_user=Depends(get_current_user_or_ak)):
    """
    转发到宿主机刷新代理的 /browsers，探测宿主 OS（macOS/Windows）上已安装的浏览器。

    探测必须在宿主机做：容器是 Linux，看不到宿主浏览器。代理不在线时降级返回
    空列表 + agent_offline=True，前端据此提示。
    """
    import urllib.request

    agent_url = (os.environ.get("WEREAD_REFRESH_AGENT_URL")
                 or "http://host.docker.internal:9876").strip()
    if agent_url.endswith("/refresh"):
        agent_url = agent_url[: -len("/refresh")]
    agent_url = agent_url.rstrip("/") + "/browsers"
    try:
        req = urllib.request.Request(agent_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return success_response({
            "browsers": payload.get("browsers", []),
            "agent_offline": False,
        })
    except Exception as e:
        return success_response({
            "browsers": [],
            "agent_offline": True,
            "message": "宿主刷新代理不可达：%s" % e,
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

    cookie_str = config_cookie or (req.cookie.strip() if req.cookie else data.get("cookie", ""))
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

    if not config_cookie:
        data["cookie"] = cookie_str
    if req.ticket is not None:
        data["ticket"] = req.ticket.strip()
    if not app_cfg.get("weread.vid", ""):
        data["vid"] = vid
    data["name"] = (req.name or "").strip() or data.get("name", "")

    _save_weread_data(data)

    return success_response({
        "vid": vid,
        "name": data.get("name", ""),
    }, "Cookie 保存成功")


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
    """Use an existing MP feed to validate Cookie and x-wr-ticket together."""
    from core.db import DB
    from core.models.feed import Feed
    from core.wx.model.weread_mp import MpsWereadMP, WereadMPAPIError, parse_mp_articles

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
        payload = wx._get_mp_articles_page(mp_id, offset=0)
        articles, _group_count = parse_mp_articles(payload)
    except WereadMPAPIError as exc:
        return error_response(400, str(exc), {
            "code": exc.code,
            "retriable": exc.retriable,
        })

    return success_response({
        "mp_id": mp_id,
        "article_count": len(articles),
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


@router.post("/collect", summary="手动采集微信读书笔记")
async def collect_weread_notes(
    req: WereadCollectRequest,
    current_user=Depends(get_current_user_or_ak),
):
    """
    手动触发微信读书笔记采集

    如果指定了 faker_id (bookId)，则只采集该书的笔记
    如果未指定，则采集整个书架上所有书的笔记
    """
    if not req.mp_id:
        return error_response(400, "mp_id 不能为空")

    from core.wx.model.weread import MpsWeread
    from core.models import Article

    wx = MpsWeread()
    wx._load_weread_auth()

    if not wx._weread_cookies:
        return error_response(400, "请先配置微信读书 Cookie")

    articles = []

    def save_callback(data: dict) -> bool:
        """回调：将笔记存入数据库"""
        from core.db import DB
        from datetime import datetime

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

    wx.get_Articles(
        faker_id=req.faker_id or None,
        Mps_id=req.mp_id,
        Mps_title=req.mp_name or req.faker_id or "微信读书",
        CallBack=save_callback,
        MaxPage=1,
        interval=3,
        Gather_Content=req.gather_content,
    )

    return success_response({
        "collected": len(articles),
        "articles": articles[:20],  # 只返回前20条
    }, f"采集完成，共 {len(articles)} 条笔记")


@router.delete("/cookie", summary="清除微信读书 Cookie")
async def clear_weread_cookie(current_user=Depends(get_current_user_or_ak)):
    """清除已保存的微信读书 Cookie"""
    if any(app_cfg.get(key, "") for key in ("weread.cookie", "weread.ticket", "weread.vid")):
        return error_response(409, "凭据由 config.yaml 或环境变量管理，请在部署配置中清除")
    data = _load_weread_data()
    data["cookie"] = ""
    data["ticket"] = ""
    data["vid"] = ""
    # 保留 name
    _save_weread_data(data)

    return success_response(message="Cookie 已清除")


# ---- 微信读书扫码授权 API ----

def _weread_qr_callback(result: dict):
    """
    扫码成功后的回调：将 Cookie 保存到 data/wx.lic
    此函数由 driver/weread_qr.py 在登录成功时自动调用
    """
    pass  # 保存逻辑已在 WereadQRLogin._save_cookies_to_lic 中实现


@router.get("/qr/code", summary="获取微信读书登录二维码")
async def get_weread_qrcode(current_user=Depends(get_current_user)):
    """
    获取微信读书扫码登录二维码
    返回二维码图片 URL（本地静态路径或外部链接）
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
