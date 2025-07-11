from core.lax.template_parser import TemplateParser
import logging

# 设置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 测试数据
articles = [
    {"title": "文章1", "publish_time": "2023-01-01","content": "测试内容"},
    {"title": "文章2", "publish_time": "2023-01-02","content": "测试内容"},
    {"title": "文章3", "publish_time": "2023-01-03","content": "测试内容"}
]

# 问题模板
template = """
{
"articles":[{% for article in articles %}
{{article}}
{% if not loop.last %},{% endif %}{% endfor %}]
}
"""
template2 = """{
 "feed": "测试feed",
 "id": "测试feed",
 "articles": [
 {"title": "文章1", "pub_date": "2023-01-01"},
 {"title": "文章2", "pub_date": "2023-01-02"},
 {"title": "文章3", "pub_date": "2023-01-03"}
 ]
}"""
def main():
    # 测试模板1
    parser = TemplateParser(template)
    result = parser.render({'articles': articles, 'feed': {'mp_name': '测试feed'}})
    print(result)
    last_comma_pos = result.rfind(',]')
    if last_comma_pos>0:
        print("❌ 错误: 最后一个元素后仍有逗号")
    else:
        print("✅ 正确: 最后一个元素后没有逗号")
    
    parser2 = TemplateParser(template2)
    result2 = parser2.render({'articles': articles, 'feed': {'mp_name': '测试feed'}})
    print(result2)
    last_comma_pos = result2.rfind(',]')
    if last_comma_pos>0:
        print("❌ 错误: 最后一个元素后仍有逗号")
    else:
        print("✅ 正确: 最后一个元素后没有逗号")

if __name__ == "__main__":
    main()