from .token import set_token
from .auth_state import is_expired
from core.print import print_warning,print_success
from core.redis_client import redis_client
#判断是否是有效登录

# 初始化全局变量（作为Redis不可用时的回退）
WX_LOGIN_ED = False
WX_LOGIN_INFO = None

import threading

# 初始化线程锁
login_lock = threading.Lock()

# Redis key 常量
REDIS_KEY_STATUS = "werss:login:status"

def setStatus(status:bool):
    """设置登录状态，优先存储到Redis，失败则使用全局变量"""
    global WX_LOGIN_ED
    # 尝试存储到Redis
    if redis_client.is_connected:
        try:
            redis_client._client.set(REDIS_KEY_STATUS, "1" if status else "0")
        except Exception:
            pass
    # 同时更新全局变量作为回退
    with login_lock:
        WX_LOGIN_ED = status

def _is_logged_in_value(value) -> bool:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return value == "1"

def _send_expired_notification(reason: str):
    try:
        from jobs.failauth import send_wx_code
        thread = threading.Thread(target=send_wx_code, args=(reason,), daemon=True)
        thread.start()
    except Exception as e:
        print_warning(f"发送授权过期通知失败: {e}")

def invalidateStatus(reason: str = "公众号平台登录失效,请重新登录") -> bool:
    """将登录状态原子切换为失效，并且每次有效期只通知一次。"""
    global WX_LOGIN_ED

    previous_redis_status = None
    redis_updated = False
    if redis_client.is_connected:
        try:
            previous_redis_status = redis_client._client.getset(REDIS_KEY_STATUS, "0")
            redis_updated = True
        except Exception as e:
            print_warning(f"更新登录失效状态失败: {e}")

    with login_lock:
        previous_local_status = WX_LOGIN_ED
        WX_LOGIN_ED = False

    if redis_updated and previous_redis_status is not None:
        transitioned = _is_logged_in_value(previous_redis_status)
    elif redis_updated:
        try:
            transitioned = previous_local_status or bool((getLoginInfo() or {}).get("token"))
        except Exception:
            transitioned = previous_local_status
    else:
        transitioned = previous_local_status

    if transitioned:
        _send_expired_notification(reason)

    return transitioned

def getStatus():
    """获取登录状态，优先从Redis读取，失败则使用全局变量，并检查token是否过期"""
    global WX_LOGIN_ED

    status = None
    if redis_client.is_connected:
        try:
            val = redis_client._client.get(REDIS_KEY_STATUS)
            if val is not None:
                status = _is_logged_in_value(val)
        except Exception as e:
            print_warning(f"检查登录状态失败: {e}")

    if status is None:
        with login_lock:
            status = WX_LOGIN_ED

    if not status:
        return False

    try:
        token_data = getLoginInfo()
    except Exception as e:
        print_warning(f"读取Token状态失败: {e}")
        return status

    if not token_data or not token_data.get('token'):
        print_warning("Token不存在，需要重新登录")
        invalidateStatus("Token不存在，请重新扫码登录")
        return False

    expiry = token_data.get('expiry') if token_data else None
    if expiry and is_expired(expiry):
        print_warning("Token已过期，需要重新登录")
        invalidateStatus("Token已过期，请重新扫码登录")
        return False

    return True

def getLoginInfo():
    from driver.token import _get_token_data
    return _get_token_data()

def Success_Msg(data:dict,ext_data:dict={}):
    from jobs.notice import sys_notice
    from core.config import cfg
    text="# 授权成功\n"
    text+=f"- 服务名：{cfg.get('server.name','')}\n"
    text+=f"- 名称：{ext_data['wx_app_name']}\n"
    text+=f"- Token: {data['token']}\n"
    text+=f"- 有效时间: {data['expiry']['expiry_time']}\n"
    
    sys_notice(text, str(cfg.get("server.code_title","WeRss授权完成")))
def Success(data:dict,ext_data:dict={}):
    if data != None:
            # print("\n登录结果:")
            if ext_data is not {}:
                print_success(f"名称：{ext_data['wx_app_name']}")
            if data['expiry'] !=None:
                Success_Msg(data,ext_data)
                print_success(f"有效时间: {data['expiry']['expiry_time']} (剩余秒数: {data['expiry']['remaining_seconds']}) Token: {data['token']}")
                set_token(data,ext_data)
                setStatus(True)
            else:
                print_warning("登录失败，请检查上述错误信息")
                setStatus(False)

    else:
            print("\n登录失败，请检查上述错误信息")
            setStatus(False)

def CanGetToken():
    """检查是否可以获取Token，包括检查登录状态和token过期时间"""
    if not getStatus():
        print_warning("当前未登录，请先扫码登录")
        return False

    # 检查token过期时间
    token_data = getLoginInfo()
    if not token_data or not token_data.get('token'):
        print_warning("Token不存在，请重新登录")
        invalidateStatus("Token不存在，请重新扫码登录")
        return False

    return True
