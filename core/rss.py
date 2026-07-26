import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import os
import json
from core.article_content import clean_article_content
from core.content_format import format_content


def select_article_content(article) -> str:
    """Return cleaned content without exposing a legacy raw WeChat document."""
    cleaned_content = (getattr(article, "content_html", None) or "").strip()
    if cleaned_content:
        return cleaned_content

    return clean_article_content(getattr(article, "content", None))


def should_filter_articles_without_content() -> bool:
    """Filter incomplete items only when consumers requested full content."""
    from core.config import cfg

    return bool(cfg.get("rss.full_context", False)) and bool(
        cfg.get("rss.filter_no_content", True)
    )


def prepare_rss_articles(articles, require_content: bool):
    """Attach selected content and omit incomplete articles when requested."""
    prepared = []
    for feed, article in articles:
        content = select_article_content(article)
        if require_content and not content.strip():
            continue
        prepared.append((feed, article, content))
    return prepared


class RSS:
    cache_dir = os.path.normpath("data/cache/rss")
    content_cache_dir = os.path.normpath("data/cache/content")
    rss_file="all"
    
    def __init__(self, name:str="all",cache_dir: str = None,ext:str="rss"):
        if cache_dir is not None:
            self.cache_dir = cache_dir
        self.ext=ext    
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.content_cache_dir, exist_ok=True)
        normalized_path = os.path.normpath(f"{self.cache_dir}/{name}.{ext}")
        if not normalized_path.startswith(self.cache_dir):
            raise ValueError("Invalid file path: Path traversal detected.")
        self.rss_file = normalized_path
        pass
    def get_type(self):
        if self.ext in ["rss","atom","md","txt"]:
            return "application/xml"
        if self.ext=="json":
            return "application/json"
        return "text/plain"
    
    def cache_content(self, content_id: str, content: dict):
        """缓存文章内容"""
        content["content"]=self.add_logo_prefix_to_urls(content["content"])
        content_path = os.path.normpath(f"{self.content_cache_dir}/{content_id}.json")
        if not content_path.startswith(self.content_cache_dir):
            raise ValueError("Invalid content path: Path traversal detected.")
        
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    def get_cached_content(self, content_id: str) -> dict:
        """获取缓存的文章内容"""
        content_path = os.path.normpath(f"{self.content_cache_dir}/{content_id}.json")
        if not content_path.startswith(self.content_cache_dir):
            raise ValueError("Invalid content path: Path traversal detected.")
        
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
    def serialize_datetime(self,obj):
        if isinstance(obj, datetime):
            return obj.isoformat
        return obj
        
    def datetime_to_rfc822(self, dt) -> str:
        """将datetime对象或时间字符串转换为RFC 822格式的时间字符串

        Accepts either a datetime object or an ISO format string. If the
        datetime is naive (no tzinfo), assume CST (UTC+8) so that '%z' is
        populated (e.g. +0800).
        """
        # Ensure we have a datetime object
        if isinstance(dt, str):
            # datetime.fromisoformat can raise; let it propagate for invalid input
            try:
                dt_obj = datetime.fromisoformat(dt)
            except Exception:
                # Fallback: try to parse common fallback formats
                dt_obj = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        elif isinstance(dt, datetime):
            dt_obj = dt
        else:
            # Last-resort: convert to str then parse
            dt_obj = datetime.fromisoformat(str(dt))

        # If datetime is naive, attach CST (UTC+8)
        if dt_obj.tzinfo is None:
            cst = timezone(timedelta(hours=8))
            dt_obj = dt_obj.replace(tzinfo=cst)

        return dt_obj.strftime('%a, %d %b %Y %H:%M:%S %z')
    
    def add_logo_prefix_to_urls(self, text: str) -> str:
        """在字符串中所有http/https开头的图片URL前添加/static/res/logo/前缀
        
        Args:
            text: 包含URL的原始字符串
            
        Returns:
            处理后的字符串，所有图片URL前添加了前缀
        """
        import re
        # try:
        #     pattern = re.compile(r'(<img[^>]*src=["\'])(?!\/static\/res\/logo\/)([^"\']*)', re.IGNORECASE)
        #     return pattern.sub(r'\1/static/res/logo/\2', text)
        # except:
        #     return text
        return text
       
    def generate_rss(self,rss_list: dict, title: str = "Mp-We-Rss", 
                    link: str = "https://github.com/rachelos/we-mp-rss",
                    description: str = "RSS频道", language: str = "zh-CN",image_url:str=""):
        from core.config import cfg
        full_context=bool(cfg.get("rss.full_context",False))
        
        # 创建根元素(RSS标准)
        rss = ET.Element("rss", version="2.0")
        if full_context==True:
            rss.attrib["xmlns:content"] = "http://purl.org/rss/1.0/modules/content/"
        channel=ET.SubElement(rss, "channel")
        # 设置渠道信息
        ET.SubElement(channel, "title").text = title
        ET.SubElement(channel, "link").text = link
        ET.SubElement(channel, "description").text = description
        ET.SubElement(channel, "language").text = language
        ET.SubElement(channel, "generator").text = "Mp-We-Rss"
        # Use timezone-aware now (CST/UTC+8) so %z shows +0800
        ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone(timedelta(hours=8))).strftime("%a, %d %b %Y %H:%M:%S %z")
    
        # 设置image子项
        if cfg.get("rss.add_cover",False)==True and image_url != "":
            image = ET.SubElement(channel, "image")
            ET.SubElement(image, "url").text = image_url
            ET.SubElement(image, "title").text = title
            ET.SubElement(image, "link").text = link

        for rss_item in rss_list:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "id").text = rss_item["id"]
            ET.SubElement(item, "title").text = rss_item["title"]
            ET.SubElement(item, "description").text = rss_item["description"] 
            ET.SubElement(item, "guid").text = rss_item["link"]
            # 添加图片封面
            if cfg.get("rss.add_cover",False)==True:
                enclosure = ET.SubElement(item, "enclosure")
                enclosure.set("url", rss_item["image"])
                enclosure.set("length", "0")
                enclosure.set("type", "image/jpeg")
            if full_context==True:
                try:
                    if cfg.get("rss.cdata",False)==True:
                        content = f"<![CDATA[{str(rss_item['content'])}]]>"  # 使用CDATA包裹内容
                    else:
                        content = str(rss_item['content'])
                    ET.SubElement(item, "content:encoded").text = content
                except Exception as e:
                    print(f"Error adding content:encoded element: {e}")
                pass
            # ET.SubElement(item, "category").text = rss_item["category"]
            # ET.SubElement(item, "author").text = rss_item["author"]
            ET.SubElement(item, "link").text = rss_item["link"]
            ET.SubElement(item, "pubDate").text = self.datetime_to_rfc822(str(rss_item["updated"]))

        # 生成XML字符串(添加声明和美化输出)
        tree_str = '<?xml version="1.0" encoding="utf-8"?>\r\n' + \
                ET.tostring(rss, encoding="utf-8", method="xml", short_empty_elements=False).decode("utf-8")
        
        if self.rss_file is not None:
            with open(self.rss_file, "w", encoding="utf-8") as f:
                f.write(tree_str)
        return tree_str
     
    def generate_atom(self,rss_list: dict, title: str = "Mp-We-Rss", 
                    link: str = "https://github.com/rachelos/we-mp-rss",
                    description: str = "RSS频道", language: str = "zh-CN",image_url:str="") -> str:
        """生成Atom格式的RSS内容
        
        Args:
            rss_list: RSS条目列表
            title: 频道标题
            link: 频道链接
            description: 频道描述
            language: 语言
            
        Returns:
            Atom格式的XML字符串
        """
        from core.config import cfg
        full_context = bool(cfg.get("rss.full_context", False))
        
        # 创建根元素(Atom标准)
        feed = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")
        if full_context==True:
            feed.attrib["xmlns:content"] = "http://purl.org/rss/1.0/modules/content/"
        ET.SubElement(feed, "title").text = title
        ET.SubElement(feed, "link",rel="alternate", href=link)
        ET.SubElement(feed, "link",rel="icon", href=image_url)
        ET.SubElement(feed, "logo").text=str(image_url)
        ET.SubElement(feed, "icon").text=str(image_url)
        # Use timezone-aware now (CST/UTC+8) so %z shows +0800
        ET.SubElement(feed, "updated").text = datetime.now(timezone(timedelta(hours=8))).strftime("%a, %d %b %Y %H:%M:%S %z")
        ET.SubElement(feed, "id").text = str(link)
        ET.SubElement(feed, "author").text = "Mp-We-Rss"
        # 设置image子项
        if cfg.get("rss.add_cover",False)==True and image_url != "":
            image = ET.SubElement(feed, "image")
            ET.SubElement(image, "url").text = str(image_url)
            ET.SubElement(image, "title").text = str(title)
            ET.SubElement(image, "link").text = str(link)
        for rss_item in rss_list:
            entry = ET.SubElement(feed, "entry")
            ET.SubElement(entry, "id").text = rss_item["id"]
            ET.SubElement(entry, "title").text = str(rss_item["title"])
            ET.SubElement(entry, "link", href=str(rss_item["link"]))
            ET.SubElement(entry, "updated").text =self.datetime_to_rfc822(str(rss_item["updated"]))
            ET.SubElement(entry, "summary").text = str(rss_item["description"])
            ET.SubElement(entry, "author").text = str(rss_item["mp_name"])
             # 添加图片封面
            if cfg.get("rss.add_cover",False)==True:
                enclosure = ET.SubElement(entry, "enclosure")
                enclosure.set("url", str(rss_item["image"]))
                enclosure.set("length", "0")
                enclosure.set("type", "image/jpeg")
            
            if full_context:
                type=self.get_content_type()
                # content = ET.SubElement(entry, "content", type=f"{str(type)}") 
                # content.text = format_content(rss_item["content"],type)
                content=format_content(rss_item["content"],type)
                try:
                    if cfg.get("rss.cdata",False)==True:
                        content = f"<![CDATA[{content}]]>"  # 使用CDATA包裹内容
                    else:
                        ET.SubElement(entry, "content:encoded").text = content
                except Exception as e:
                    print(f"Error adding content:encoded element: {e}")
                pass
        # 生成XML字符串
        tree_str = '<?xml version="1.0" encoding="utf-8"?>\r\n' + \
                  ET.tostring(feed, encoding="utf-8", method="xml").decode("utf-8")
        
        if self.rss_file is not None:
            with open(self.rss_file, "w", encoding="utf-8") as f:
                f.write(tree_str)
        return tree_str
    def set_content_type(self,type:str=None):
        self.content_type=type
    def get_content_type(self)->str:
        ext=self.ext
        if ext in("atom","xml","json","markdown"):
            return "html",
        elif ext in("md","jmd"):
            return "markdown"
        elif ext in("txt"):
            return "text"
        return "html"
    def generate_json(self, rss_list: dict,title: str = "Mp-We-Rss", 
                    link: str = "https://github.com/rachelos/we-mp-rss",
                    description: str = "RSS频道", language: str = "zh-CN",image_url:str="") -> str:
        """获取JSON格式的RSS内容
        
        Args:
            rss_list: RSS条目列表
            
        Returns:
            JSON格式的字符串
        """
        type=self.get_content_type()
        result = {
            "name":title,
            "link":link,
            "description":description,
            "language": language,
            "cover":image_url,
            "items": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "description": item["description"],
                    "link": item["link"],
                    "updated": item["updated"].isoformat() if isinstance(item["updated"], datetime) else item["updated"],
                    "content": format_content(item["content"],type),
                    "channel_name": item.get("mp_name", ""),
                    "feed": item.get("feed")
                } for item in rss_list
            ]
        }
        return json.dumps(result, ensure_ascii=False, indent=2, default=self.serialize_datetime)

    def get_cache(self):
        if not hasattr(self, 'rss_file') or not self.rss_file:
               return None
        try:
            with open(self.rss_file, "r", encoding="utf-8") as f:
                return f.read()  
        except FileNotFoundError:
            return None     
    def generate(self,rss_list: dict,ext=str, title: str = "Mp-We-Rss", 
                    link: str = "https://github.com/rachelos/we-mp-rss",
                    description: str = "RSS频道", language: str = "zh-CN",image_url:str="",template:str=None) -> str:
        """根据扩展名获取对应格式的RSS内容
        
        Args:
            rss_list: RSS条目列表
            ext: 文件扩展名(.rss/.xml/.atom/.json)
            **kwargs: 传递给各格式生成方法的参数
            
        Returns:
            对应格式的字符串
            
        Raises:
            ValueError: 当扩展名不支持时
        """
        ext = ext.lower().strip('.')
        self.ext=ext
        if ext in ('rss', 'xml'):
            return self.generate_rss(rss_list, title=title, link=link, description=description,language=language,image_url=image_url)
        elif ext in ('atom','md','txt'):
            return self.generate_atom(rss_list, title=title, link=link, description=description,language=language,image_url=image_url)
        elif ext in ('json','jmd'):
            return self.generate_json(rss_list, title=title, link=link, description=description,language=language,image_url=image_url)
        elif template is not None:
            return self.generate_by_template(rss_list,template, title=title, link=link, description=description,language=language,image_url=image_url)
        else:
            raise ValueError(f"Unsupported extension: {ext}")
    def generate_by_template(self,rss_list: dict, template: str, title: str = "Mp-We-Rss",link: str = "https://github.com/rachelos/we-mp-rss",description: str = "RSS频道",language: str = "zh-CN",image_url:str=""):
            from core.lax import TemplateParser
            template = TemplateParser(template)
            return template.render({"articles": rss_list, "title": title,"link":link,"description":description,"language":language,"image_url":image_url})
            pass
    def clear_cache(self,mp_id:str=""):

        """清除所有缓存文件
        
        删除data/cache/rss和data/cache/content目录中包含'mp_id'的文件
        保持与现有方法相同的路径安全检查机制
        """
        import shutil
        
        # 清除rss缓存目录
        if os.path.exists(self.cache_dir):
            for filename in os.listdir(self.cache_dir):
                if f'{mp_id}_' not in filename:
                    continue
                file_path = os.path.normpath(f"{self.cache_dir}/{filename}")
                if not file_path.startswith(self.cache_dir):
                    raise ValueError("Invalid file path: Path traversal detected.")
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")
