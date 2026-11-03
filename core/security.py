"""高风险 Web 功能默认关闭，仅允许显式启用后的管理员访问。"""

from fastapi import HTTPException, Request
from core.auth import get_current_user_or_ak, oauth2_scheme
from core.config import cfg


async def require_trusted_admin(request: Request, setting: str):
    # 缺少配置或配置类型不正确时保持关闭，不将字符串 "false" 当作真值。
    if cfg.get(setting, False) is not True:
        raise HTTPException(status_code=403, detail="This high-risk web feature is disabled")
    token = await oauth2_scheme(request)
    if not token and not request.headers.get("Authorization", "").startswith("AK-SK "):
        raise HTTPException(status_code=401, detail="Authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    user = await get_current_user_or_ak(request, token=token)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


async def require_web_updater(request: Request):
    return await require_trusted_admin(request, "safe.enable_web_updater")


async def guard_rss_template(request: Request):
    # 在读缓存、访问数据库前拦截，包括空模板；普通 RSS 订阅保持匿名可读。
    if "template" in request.query_params:
        await require_trusted_admin(request, "safe.enable_custom_rss_template")
