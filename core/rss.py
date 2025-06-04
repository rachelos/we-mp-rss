import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
class RSS:
    cache_dir = "static/cache/rss"
    rss_file="all"
    def __init__(self, name:str="all",cache_dir: str = None):
        if cache_dir is not None:
            self.cache_dir = cache_dir
      
        os.makedirs(self.cache_dir, exist_ok=True)
        normalized_path = os.path.normpath(f"{self.cache_dir}/{name}.xml")
        if not normalized_path.startswith(os.path.abspath(self.cache_dir)):
            raise ValueError("Invalid file path: Path traversal detected.")
        self.rss_file = normalized_path
        pass
    def serialize_datetime(self,obj):
        if isinstance(obj, datetime):
            return obj.isoformat
        return obj
    def get_rss(self,name:str="all"):
        if not hasattr(self, 'rss_file') or not self.rss_file:
            return None
        try:
            with open(self.rss_file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None 
    def generate_rss(self,rss_list: dict, title: str = "Mp-We-Rss", 
                    author: str = "Rachel", link: str = "https://github.com/rachelos/we-mp-rss",
                    description: str = "RSS频道", language: str = "zh-CN",others: dict = None):
        # 创建根元素(RSS标准)
        rss = ET.Element("rss", version="2.0")
        rss.attrib["xmlns"] = "http://www.w3.org/2005/Atom"
        channel=ET.SubElement(rss, "channel")
        # 设置渠道信息
        ET.SubElement(channel, "title").text = title
        ET.SubElement(channel, "link").text = link
        ET.SubElement(channel, "description").text = description
        ET.SubElement(channel, "language").text = language
        ET.SubElement(channel, "generator").text = "Mp-We-Rss"
        ET.SubElement(channel, "lastBuildDate").text = self.serialize_datetime(datetime.now().isoformat())
        author_elem = ET.SubElement(channel, "author")
        ET.SubElement(author_elem, "name").text = author
        if others is not None:
            for key, value in others.items():
                ET.SubElement(channel, key).text = value
        # 添加项目条目(取消注释并修改为RSS标准)
        for rss_item in rss_list:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "id").text = rss_item["id"]
            ET.SubElement(item, "title").text = rss_item["title"]
            ET.SubElement(item, "description").text = rss_item["description"]
            ET.SubElement(item, "guid").text = rss_item["link"]
            link=ET.SubElement(item, "link")
            link.text = rss_item["link"]
            link.attrib["href"] = rss_item["link"]

            ET.SubElement(item, "pubDate").text = rss_item["updated"]

        # 生成XML字符串(添加声明和美化输出)
        tree_str = '<?xml version="1.0" encoding="utf-8"?>\r\n' + \
                ET.tostring(rss, encoding="utf-8", method="xml", short_empty_elements=False).decode("utf-8")
        
        if self.rss_file is not None:
            with open(self.rss_file, "w", encoding="utf-8") as f:
                f.write(tree_str)
        return tree_str