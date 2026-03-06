from .wechat import send_wechat_message
from .dingtalk import send_dingtalk_message
from .feishu import send_feishu_message
from .custom import send_custom_message
from .bark import send_bark_message
import re
from urllib.parse import urlparse


def _is_bark_url(webhook_url: str) -> bool:
    url = (webhook_url or "").strip()
    if not url:
        return False

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path_parts = [p for p in (parsed.path or "").split("/") if p]

    # 官方 Bark 服务域名
    if "day.app" in host:
        return True


    # Bark 直连写法: https://<host>/<device_key>
    if path_parts and re.fullmatch(r"[A-Za-z0-9_-]{16,128}", path_parts[-1]):
        return True

    return False


def notice( webhook_url, title, text,notice_type: str=None):
    """
    公用通知方法，根据类型判断调用哪种通知
    
    参数:
    - notice_type: 通知类型，'wechat' 或 'dingtalk'
    - webhook_url: 对应机器人的Webhook地址
    - title: 消息标题
    - text: 消息内容
    """
    if len(str(webhook_url)) == 0:
        raise ValueError('未提供webhook_url')
        return
    # 优先notice_type；未传入时才按 URL 自动识别
    if not notice_type:
        if 'qyapi.weixin.qq.com' in webhook_url:
            notice_type = 'wechat'
        elif 'oapi.dingtalk.com' in webhook_url:
            notice_type = 'dingtalk'
        # 兼容企业本地化部署的飞书，如open.feishu.xxxx.com
        elif 'open.feishu.' in webhook_url:
            notice_type = 'feishu'
        elif _is_bark_url(webhook_url):
            notice_type = 'bark'
        else:
            notice_type = 'custom'
    
    if notice_type == 'wechat':
        send_wechat_message(webhook_url, title, text)
    elif notice_type == 'dingtalk':
        send_dingtalk_message(webhook_url, title, text)
    elif notice_type == 'feishu':
        send_feishu_message(webhook_url, title, text)
    elif notice_type == 'bark':
        send_bark_message(webhook_url, title, text)
    elif notice_type == 'custom':
        send_custom_message(webhook_url, title, text)
    else:
        raise ValueError(f'不支持的通知类型: {notice_type}')