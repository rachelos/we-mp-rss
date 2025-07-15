import requests
import json


def send_custom_message(webhook_url, title, text):
    """
    发送微信消息
    
    参数:
    - webhook_url: 自定义Webhook地址
    - title: 消息标题
    - text: 消息内容
    """
    headers = {'Content-Type': 'application/json'}
    data = {
        "title": title,
        "content": text
    }
    try:
        response = requests.post(
            url=webhook_url,
            headers=headers,
            data=json.dumps(data)
        )
        print(response.text)
    except Exception as e:
        print('自定义webhook通知发送失败', e)