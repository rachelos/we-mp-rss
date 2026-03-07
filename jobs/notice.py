from core.config import cfg
def sys_notice(text:str="",title:str="",tag:str='系统通知',type=""):
    from core.notice import notice
    markdown_text = f"### {title} {type} {tag}\n{text}"
    notice_cfg = cfg.get('notice', {}) or {}
    webhook = notice_cfg.get('dingding', '')
    if len(webhook)>0:
        notice(webhook, title, markdown_text)
    feishu_webhook = notice_cfg.get('feishu', '')
    if len(feishu_webhook)>0:
        notice(feishu_webhook, title, markdown_text)
    wechat_webhook = notice_cfg.get('wechat', '')
    if len(wechat_webhook)>0:
        notice(wechat_webhook, title, markdown_text)
    custom_webhook = notice_cfg.get('custom', '')
    if len(custom_webhook)>0:
        notice(custom_webhook, title, markdown_text)
    bark_webhook = notice_cfg.get('bark', '')
    if len(bark_webhook)>0:
        notice(bark_webhook, title, markdown_text, notice_type='bark')

