from core.models.message_task import MessageTask
from core.models.feed import Feed
from core.models.article import Article
from core.print import print_success
from core.notice import notice
from dataclasses import dataclass
from core.lax import TemplateParser
from datetime import datetime
from core.log import logger
@dataclass
class MessageWebHook:
    task: MessageTask
    feed:Feed
    articles: list[Article]
    pass

def send_message(hook: MessageWebHook) -> str:
    """
    发送格式化消息
    
    参数:
        hook: MessageWebHook对象，包含任务、订阅源和文章信息
        
    返回:
        str: 格式化后的消息内容
    """
    template = hook.task.message_template if hook.task.message_template else """
### {{feed.mp_name}} 订阅消息：
{% if articles %}
{% for article in articles %}
- [**{{ article.title }}**]({{article.url}}) ({{ article.publish_time }})\n
{% endfor %}
{% else %}
- 暂无文章\n
{% endif %}
    """
    parser = TemplateParser(template)
    data = {
        "feed": hook.feed,
        "articles": hook.articles,
        "task": hook.task,
        'now': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    message = parser.render(data)
    # 这里可以添加发送消息的具体实现
    print("发送消息:", message)
    notice(hook.task.web_hook_url, hook.task.name, message)
    return message

def call_webhook(hook: MessageWebHook) -> str:
    """
    调用webhook接口发送数据
    
    参数:
        hook: MessageWebHook对象，包含任务、订阅源和文章信息
        
    返回:
        str: 调用结果信息
        
    异常:
        ValueError: 当webhook调用失败时抛出
    """
    template = hook.task.message_template if hook.task.message_template else """{
        "articles": [
            {% for article in articles %}
             {{article}}{% if not loop.last %},{% endif %}{% endfor %}]
            {% endfor %}
        ]
    }"""
    parser = TemplateParser(template)
    data = {
        "feed": hook.feed,
        "articles": hook.articles,
        "task": hook.task,
        'now': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    payload = parser.render(data)
    
    # 检查web_hook_url是否为空
    if not hook.task.web_hook_url:
        logger.error("web_hook_url为空")
        return 
    # 发送webhook请求
    import requests
    # print_success(f"发送webhook请求{payload}")
    try:
        response = requests.post(
            hook.task.web_hook_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return "Webhook调用成功"
    except Exception as e:
        raise ValueError(f"Webhook调用失败: {str(e)}")

def web_hook(hook:MessageWebHook):
    """
    根据消息类型路由到对应的处理函数
    
    参数:
        hook: MessageWebHook对象，包含任务、订阅源和文章信息
        
    返回:
        对应处理函数的返回结果
        
    异常:
        ValueError: 当消息类型未知时抛出
    """
    try:
        # 处理articles参数，兼容Article对象和字典类型
        processed_articles = []
        if len(hook.articles)<=0:
            # raise ValueError("没有更新到文章")
            logger.warning("没有更新到文章")
            return 
        for article in hook.articles:
            if isinstance(article, dict):
                # 如果是字典类型，直接使用
                processed_article = {
                    field.name: (
                        datetime.fromtimestamp(article[field.name]).strftime("%Y-%m-%d %H:%M:%S")
                        if field.name == "publish_time" and field.name in article
                        else article.get(field.name, "")
                    )
                    for field in Article.__table__.columns
                }
            else:
                # 如果是Article对象，使用getattr获取属性
                processed_article = {
                    field.name: (
                        datetime.fromtimestamp(getattr(article, field.name)).strftime("%Y-%m-%d %H:%M:%S")
                        if field.name == "publish_time"
                        else getattr(article, field.name)
                    )
                    for field in Article.__table__.columns
                }
            processed_articles.append(processed_article)
        
        hook.articles = processed_articles
        
        if hook.task.message_type == 0:  # 发送消息
            return send_message(hook)
        elif hook.task.message_type == 1:  # 调用webhook
            return call_webhook(hook)
        else:
            raise ValueError(f"未知的消息类型: {hook.task.message_type}")
    except Exception as e:
        raise ValueError(f"处理消息时出错: {str(e)}")