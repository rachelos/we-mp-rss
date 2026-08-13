import requests
import json

def send_feishu_message(webhook_url, title, text):
    """
    发送飞书 Markdown 格式消息
    
    参数:
    - webhook_url: 飞书机器人 Webhook 地址
    - title: 消息标题
    - text: Markdown 格式内容
    """
    headers = {'Content-Type': 'application/json'}
    data = {
        "msg_type": "interactive",
        "card": {
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "content": text,
                        "tag": "lark_md"
                    }
                }
            ],
            "header": {
                "template": "blue",
                "title": {
                    "content": title,
                    "tag": "plain_text"
                }
            }
        }
    }
    try:
        response = requests.post(
            url=webhook_url,
            headers=headers,
            data=json.dumps(data),
            timeout=30
        )
        print(response.text)
    except Exception as e:
        print('飞书通知发送失败', e)