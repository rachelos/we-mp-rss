"""
微信新版"自由发布"接口采集器
替代已被限制的 /cgi-bin/appmsgpublish 和 /cgi-bin/appmsg

微信后台新版架构:
  - 旧流程: 素材管理(appmsg) → 群发(appmsgpublish)
  - 新流程: 草稿管理(draft) → 自由发布(free_publish)

本模块提供两级采集策略:
  1. 优先使用新版 free_publish 接口
  2. 自动降级到旧版 appmsgpublish/appmsg 接口
  3. 支持 Playwright 浏览器模式兜底
"""

import json
import requests
import time
import random
from core.wx.base import WxGather
from core.print import print_error, print_info, print_warning
from core.log import logger


class MpsFreePublish(WxGather):
    """
    新版自由发布采集器
    
    支持的接口端点（按优先级）:
    1. /cgi-bin/free_publish?action=list        - 新版"已发表"列表
    2. /cgi-bin/publish?action=publish_list     - 备用新版发布列表
    3. /cgi-bin/appmsgpublish?sub=list           - 旧版发布管理（降级）
    4. /cgi-bin/appmsg?action=list_ex            - 旧版素材管理（降级）
    """

    # 多端点配置
    ENDPOINTS = [
        {
            "name": "free_publish",
            "url": "https://mp.weixin.qq.com/cgi-bin/free_publish",
            "params": {
                "action": "list",
                "begin": 0,
                "count": 5,
                "fakeid": "",
                "token": "",
                "lang": "zh_CN",
                "f": "json",
                "ajax": 1,
            },
            "list_key": "free_publish_list",  # 响应中的列表字段
            "item_parser": "parse_free_publish_item",
        },
        {
            "name": "publish",
            "url": "https://mp.weixin.qq.com/cgi-bin/publish",
            "params": {
                "action": "publish_list",
                "begin": 0,
                "count": 5,
                "fakeid": "",
                "token": "",
                "lang": "zh_CN",
                "f": "json",
                "ajax": 1,
            },
            "list_key": "publish_list",
            "item_parser": "parse_publish_item",
        },
        {
            "name": "appmsgpublish",
            "url": "https://mp.weixin.qq.com/cgi-bin/appmsgpublish",
            "params": {
                "sub": "list",
                "sub_action": "list_ex",
                "begin": 0,
                "count": 5,
                "fakeid": "",
                "token": "",
                "lang": "zh_CN",
                "f": "json",
                "ajax": 1,
            },
            "list_key": None,  # 数据在 publish_page.publish_list 中
            "item_parser": "parse_appmsgpublish_item",
        },
        {
            "name": "appmsg",
            "url": "https://mp.weixin.qq.com/cgi-bin/appmsg",
            "params": {
                "action": "list_ex",
                "begin": 0,
                "count": 5,
                "fakeid": "",
                "type": "9",
                "token": "",
                "lang": "zh_CN",
                "f": "json",
                "ajax": "1",
            },
            "list_key": "app_msg_list",
            "item_parser": "parse_appmsg_item",
        },
    ]

    def content_extract(self, url):
        """重写内容提取方法"""
        try:
            from driver.wxarticle import Web as App
            r = App.get_article_content(url)
            if r is not None:
                text = r.get("content", "")
                return text
        except Exception as e:
            logger.error(e)
        return ""

    def get_Articles(
        self,
        faker_id: str = None,
        Mps_id: str = None,
        Mps_title="",
        CallBack=None,
        start_page: int = 0,
        MaxPage: int = 1,
        interval=10,
        Gather_Content=False,
        Item_Over_CallBack=None,
        Over_CallBack=None,
    ):
        super().Start(mp_id=Mps_id)
        if self.Gather_Content:
            Gather_Content = True
        print(f"多端点降级模式,是否采集[{Mps_title}]内容：{Gather_Content}\n")

        count = 5
        session = self.session

        # 逐个尝试各个端点
        effective_endpoint = None
        for endpoint_config in self.ENDPOINTS:
            endpoint_name = endpoint_config["name"]
            print_info(f"尝试端点: {endpoint_name}")

            # 测试第一个页面的请求
            test_params = endpoint_config["params"].copy()
            test_params["begin"] = 0
            test_params["fakeid"] = faker_id
            test_params["token"] = self.token

            test_url = endpoint_config["url"]
            try:
                headers = self.fix_header(test_url)
                resp = session.get(
                    test_url, headers=headers, params=test_params, verify=False, timeout=15
                )
                msg = resp.json()
                ret = msg.get("base_resp", {}).get("ret", -1)

                if ret == 200013:
                    print_warning(f"{endpoint_name}: 频率限制")
                    continue
                if ret == 200003:
                    print_warning(f"{endpoint_name}: Session失效")
                    continue
                if ret != 0:
                    print_warning(
                        f"{endpoint_name}: 返回错误 ret={ret}, err_msg={msg.get('base_resp', {}).get('err_msg', '')}"
                    )
                    continue

                # 验证是否有有效数据
                parser = getattr(self, endpoint_config.get("item_parser", ""), None)
                list_key = endpoint_config.get("list_key")
                if self._has_valid_data(msg, list_key, parser):
                    effective_endpoint = endpoint_config
                    print_success(f"端点 {endpoint_name} 可用!")
                    break
                else:
                    print_warning(f"{endpoint_name}: 响应无有效数据")

            except requests.exceptions.Timeout:
                print_warning(f"{endpoint_name}: 请求超时")
                continue
            except Exception as e:
                print_warning(f"{endpoint_name}: 请求异常: {e}")
                continue

        if effective_endpoint is None:
            try:
                from core.wx.model.weread_mp import MpsWereadMP
                wmp = MpsWereadMP()
                wmp._load_weread_auth()
                if wmp._weread_cookies:
                    print_info("所有 MP 后台端点均受限，检测到已配置微信读书 Cookie，自动切换至 weread_mp 通道...")
                    wmp.get_Articles(
                        faker_id=faker_id,
                        Mps_id=Mps_id,
                        Mps_title=Mps_title,
                        CallBack=CallBack,
                        start_page=start_page,
                        MaxPage=MaxPage,
                        interval=interval,
                        Gather_Content=Gather_Content,
                        Item_Over_CallBack=Item_Over_CallBack,
                        Over_CallBack=Over_CallBack,
                    )
                    return
            except Exception as e:
                print_warning(f"降级到 weread_mp 失败: {e}")

            if getattr(self, "_auto_fallback", False):
                try:
                    print_info("自动降级到 Playwright 浏览器模式...")
                    from core.wx.model.playwright_mp import MpsPlaywright
                    pw = MpsPlaywright()
                    pw.token = self.token
                    pw.cookies = self.cookies
                    pw.get_Articles(
                        faker_id=faker_id,
                        Mps_id=Mps_id,
                        Mps_title=Mps_title,
                        CallBack=CallBack,
                        start_page=start_page,
                        MaxPage=MaxPage,
                        interval=interval,
                        Gather_Content=Gather_Content,
                        Item_Over_CallBack=Item_Over_CallBack,
                        Over_CallBack=Over_CallBack,
                    )
                    return
                except Exception as e:
                    print_warning(f"降级到 Playwright 失败: {e}")

            super().Error("所有端点均不可用，请检查登录状态或配置微信读书(weread_mp)/Playwright模式")
            super().Over(CallBack=Over_CallBack)
            return

        # 使用有效端点开始采集
        url = effective_endpoint["url"]
        params = effective_endpoint["params"].copy()
        params["fakeid"] = faker_id
        params["token"] = self.token
        parser = getattr(self, effective_endpoint.get("item_parser", ""), None)
        list_key = effective_endpoint.get("list_key")
        item_parser_name = effective_endpoint.get("item_parser", "")

        print_info(f"使用端点 {effective_endpoint['name']} 开始采集...\n")

        i = start_page
        while True:
            if i >= MaxPage:
                break
            begin = i * count
            params["begin"] = str(begin)
            print(f"第{i+1}页开始爬取\n")
            time.sleep(random.randint(0, interval))

            try:
                headers = self.fix_header(url)
                resp = session.get(url, headers=headers, params=params, verify=False)
                msg = resp.json()
                self._cookies = resp.cookies

                ret = msg.get("base_resp", {}).get("ret", -1)
                if ret == 200013:
                    super().Error(f"frequency control, stop at {str(begin)}")
                    break
                if ret == 200003:
                    super().Error(
                        f"Invalid Session, stop at {str(begin)}", code="Invalid Session"
                    )
                    break
                if ret != 0:
                    super().Error(
                        f"错误原因:{msg['base_resp']['err_msg']}:代码:{msg['base_resp']['ret']}",
                        code=msg["base_resp"]["err_msg"],
                    )
                    break

                # 解析文章列表
                articles = self._parse_response(msg, list_key, item_parser_name)
                if not articles:
                    super().Error("all article parsed")
                    break

                for item in articles:
                    if Gather_Content:
                        if not super().HasGathered(item["aid"]):
                            item["content"] = self.content_extract(item["link"])
                            super().Wait(3, 10, tips=f"{item['title']} 采集完成")
                    else:
                        item["content"] = ""
                    item["id"] = item["aid"]
                    item["mp_id"] = Mps_id
                    if CallBack is not None:
                        super().FillBack(
                            CallBack=CallBack,
                            data=item,
                            Ext_Data={"mp_title": Mps_title, "mp_id": Mps_id},
                        )
                print(f"第{i+1}页爬取成功\n")

                i += 1

            except requests.exceptions.Timeout:
                print("Request timed out")
                break
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                break
            finally:
                super().Item_Over(
                    item={"mps_id": Mps_id, "mps_title": Mps_title},
                    CallBack=Item_Over_CallBack,
                )

        super().Over(CallBack=Over_CallBack)

    def _has_valid_data(self, msg, list_key, parser):
        """检查响应中是否有有效数据"""
        try:
            if list_key and list_key in msg:
                return len(msg[list_key]) > 0
            # appmsgpublish 特殊处理
            if "publish_page" in msg:
                pp = json.loads(msg["publish_page"]) if isinstance(msg["publish_page"], str) else msg["publish_page"]
                return len(pp.get("publish_list", [])) > 0
            return False
        except Exception:
            return False

    def _parse_response(self, msg, list_key, parser_name):
        """
        统一解析各端点的响应，返回标准化的文章列表。
        每种响应格式都会尝试解析出: aid, title, link, cover, digest, 
        create_time, update_time 等字段。
        """
        articles = []

        # 1. 标准列表键
        if list_key and list_key in msg:
            raw_list = msg[list_key]
            if isinstance(raw_list, list) and len(raw_list) > 0:
                articles = self._normalize_articles(raw_list)
                return articles

        # 2. appmsgpublish 旧格式: publish_page.publish_list[].publish_info.appmsgex[]
        if "publish_page" in msg:
            try:
                pp = (
                    json.loads(msg["publish_page"])
                    if isinstance(msg["publish_page"], str)
                    else msg["publish_page"]
                )
                for publish_item in pp.get("publish_list", []):
                    if "publish_info" in publish_item:
                        pi = (
                            json.loads(publish_item["publish_info"])
                            if isinstance(publish_item["publish_info"], str)
                            else publish_item["publish_info"]
                        )
                        if "appmsgex" in pi:
                            for art in pi["appmsgex"]:
                                art["publish_info"] = pi
                                articles.append(art)
                return articles
            except Exception as e:
                print_error(f"解析 publish_page 失败: {e}")

        # 3. 直接列表（列表中每项就是文章对象）
        if isinstance(msg, list):
            articles = self._normalize_articles(msg)
            return articles

        return articles

    def _normalize_articles(self, raw_list):
        """
        标准化文章列表，适配来自不同端点的数据格式。
        支持两种格式:
        - 直接文章列表: [{aid, title, link, cover, ...}, ...]
        - 发布项列表: [{publish_info: {appmsgex: [{...}]}}, ...]
        """
        articles = []
        for item in raw_list:
            # 格式A: 直接是文章对象
            if "aid" in item and "title" in item:
                articles.append(item)
            # 格式B: 包含 publish_info 的发布项
            elif "publish_info" in item:
                pi = item["publish_info"]
                if isinstance(pi, str):
                    try:
                        pi = json.loads(pi)
                    except Exception:
                        continue
                if "appmsgex" in pi:
                    for art in pi["appmsgex"]:
                        art["publish_info"] = pi
                        articles.append(art)
                elif "aid" in pi:
                    articles.append(pi)
            else:
                # 尝试直接添加
                if isinstance(item, dict):
                    articles.append(item)
        return articles

    # ---- 各端点的解析器（预留给可能的特殊解析逻辑） ----

    def parse_free_publish_item(self, msg):
        """free_publish 端点响应解析"""
        return self._parse_response(msg, "free_publish_list", None)

    def parse_publish_item(self, msg):
        """publish 端点响应解析"""
        return self._parse_response(msg, "publish_list", None)

    def parse_appmsgpublish_item(self, msg):
        """appmsgpublish 端点响应解析"""
        return self._parse_response(msg, None, None)

    def parse_appmsg_item(self, msg):
        """appmsg 端点响应解析"""
        return self._parse_response(msg, "app_msg_list", None)
