import requests


def send_bark_message(webhook_url, title, text):
    """
    发送 Bark 消息

    参数:
    - webhook_url: Bark 地址（例如 https://api.day.app/<device_key>）
    - title: 消息标题
    - text: 消息内容
    """
    title = (title or "WeRSS")[:200]
    text = (text or "")[:2000]

    url = (webhook_url or "").strip()
    if not url:
        raise ValueError("未提供 Bark webhook_url")

    try:
        payload = {
            "title": title,
            "markdown": text
        }
        response = requests.post(
            url=url,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10
        )
        print(payload)
        print(response.text)
    except Exception as e:
        print("Bark 通知发送失败", e)
