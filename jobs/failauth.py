from core.print import print_warning, print_info
from driver.base import WX_API
from core.config import cfg
from jobs.notice import sys_notice
from driver.success import Success
from tools.base64_tools import image_to_base64
import time


def send_wx_code(title: str = "", url: str = ""):
    """发送微信授权过期通知

    始终发送过期通知。当 send_code=True 时，尝试获取二维码并附带在通知中；
    当 send_code=False 时，只发送文字通知（不含二维码）。
    """
    # 始终发送过期通知（不依赖 send_code 配置）
    text = f"- 服务名：{cfg.get('server.name', '')}\n"
    text += f"- 发送时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n"
    if title:
        text += f"- 原因：{title}\n"

    notice_title = str(cfg.get("server.code_title", "WeRss授权过期,扫码授权"))

    if cfg.get("server.send_code", False):
        # send_code=True: 尝试获取二维码，通过回调发送含二维码的通知
        WX_API.GetCode(Notice=CallBackNotice, CallBack=Success)
    else:
        # send_code=False: 直接发送不含二维码的文字通知
        text += "- 请手动访问系统进行扫码登录"
        try:
            sys_notice(text=text, title=notice_title)
            print_info(f"已发送授权过期通知(无二维码): {notice_title}")
        except Exception as e:
            print_warning(f"发送授权过期通知失败: {e}")


def CallBackNotice(data=None, ext_data=None):
    """获取二维码过程中的回调通知"""
    if data is not None:
        print_warning(data)
        # 获取二维码出错时，发送不含二维码的通知提醒用户手动登录
        text = f"- 服务名：{cfg.get('server.name', '')}\n"
        text += f"- 发送时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n"
        text += f"- 获取二维码失败：{data}\n"
        text += "- 请手动访问系统进行扫码登录"
        try:
            sys_notice(
                text=text,
                title=str(cfg.get("server.code_title", "WeRss授权过期"))
            )
        except Exception as e:
            print_warning(f"发送二维码获取失败通知失败: {e}")
        return

    img_path = WX_API.QRcode()['code']
    rss_domain = str(cfg.get("rss.base_url", ""))
    url = rss_domain + str(img_path)
    url = image_to_base64("./static/wx_qrcode.png")
    text = f"- 服务名：{cfg.get('server.name', '')}\n"
    text += f"- 发送时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}"
    if WX_API.GetHasCode():
        text += f"![描述]({url})"
        text += f"\n- 请使用微信扫描二维码进行授权"
    sys_notice(text, str(cfg.get("server.code_title", "WeRss授权过期,扫码授权")))