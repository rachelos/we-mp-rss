
from core.config import cfg
from driver.success import Success
import time
def sys_notice(text:str="",title:str=""):
    from core.notice import notice
    markdown_text = f"### {title} 通知\n{text}"
    webhook = cfg.get('notice')['dingding']
    if len(webhook)>0:
        notice(webhook, title, markdown_text)
    feishu_webhook = cfg.get('notice')['feishu']
    if len(feishu_webhook)>0:
        notice(feishu_webhook, title, markdown_text)
    wechat_webhook = cfg.get('notice')['wechat']
    if len(wechat_webhook)>0:
        notice(wechat_webhook, title, markdown_text)
    custom_webhook = cfg.get('notice')['custom']
    if len(custom_webhook)>0:
        notice(custom_webhook, title, markdown_text)
    

from driver.wx import WX_API
def send_wx_code(title:str="",url:str=""):
    if cfg.get("server.send_code",False):
        WX_API.GetCode(Notice=CallBackNotice,CallBack=Success)
    pass
def CallBackNotice():
        url=WX_API.QRcode()['code']
        svg="""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
        <rect x="10" y="10" width="180" height="180" fill="#ffcc00" stroke="#000" stroke-width="2"/>
        </svg>
        """
        rss_domain=cfg.get("rss.base_url","")
        url=rss_domain+str(url)
        text=f"- 服务名：{cfg.get('server.name','')}\n"
        text+=f"- 发送时间： {time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))}"
        if WX_API.GetHasCode():
            text+=f"![二维码]({url})"
            text+=f"\n- 请使用微信扫描二维码进行授权"
        sys_notice(text, cfg.get("server.code_title","WeRss授权过期,扫码授权"))