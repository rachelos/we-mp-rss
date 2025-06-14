import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import json
class RSS:
    cache_dir = os.path.normpath("static/cache/rss")
    content_cache_dir = os.path.normpath("static/cache/content")
    rss_file="all"
    
    def __init__(self, name:str="all",cache_dir: str = None):
        if cache_dir is not None:
            self.cache_dir = cache_dir
      
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.content_cache_dir, exist_ok=True)
        normalized_path = os.path.normpath(f"{self.cache_dir}/{name}.xml")
        if not normalized_path.startswith(self.cache_dir):
            raise ValueError("Invalid file path: Path traversal detected.")
        self.rss_file = normalized_path
        pass

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
        
    def datetime_to_rfc822(self,dt:str)->str:
        """将datetime对象或时间字符串转换为RFC 822格式的时间字符串"""
        dt = datetime.fromisoformat(dt)
        return dt.strftime('%a, %d %b %Y %H:%M:%S %z')
    def get_rss(self,name:str="all"):
        if not hasattr(self, 'rss_file') or not self.rss_file:
            return None
        try:
            with open(self.rss_file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None 
    def generate_rss(self,rss_list: dict, title: str = "Mp-We-Rss", 
                    link: str = "https://github.com/rachelos/we-mp-rss",
                    description: str = "RSS频道", language: str = "zh-CN",
                    image_url: str = ""):
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
        ET.SubElement(channel, "lastBuildDate").text =datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
        # 设置image子项
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

    def add_logo_prefix_to_urls(self, text: str) -> str:
        """在字符串中所有http/https开头的图片URL前添加/static/res/logo/前缀
        
        Args:
            text: 包含URL的原始字符串
            
        Returns:
            处理后的字符串，所有图片URL前添加了前缀
        """
        import re
        try:
            pattern = re.compile(r'(<img[^>]*src=["\'])(?!\/static\/res\/logo\/)([^"\']*)', re.IGNORECASE)
            return pattern.sub(r'\1/static/res/logo/\2', text)
        except:
            return text