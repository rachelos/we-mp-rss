import json
import requests
import time
import random
import yaml
import re
from bs4 import BeautifulSoup
from core.wx.base import WxGather
from core.print import print_error
from core.log import logger
# 继承 BaseGather 类
class MpsApi(WxGather):

    # 重写 content_extract 方法
    def content_extract(self,  url):
        try:
            return super().content_extract(url)
        except Exception as e:
                logger.error(e)
        return ""
    # 重写 get_Articles 方法
    def get_Articles(self, faker_id:str=None,Mps_id:str=None,Mps_title="",CallBack=None,start_page=0,MaxPage:int=1,interval=10,Gather_Content=True,Item_Over_CallBack=None,Over_CallBack=None):
        super().Start(mp_id=Mps_id)
        Gather_Content = self.Gather_Content
        print(f"API获取模式,是否采集[{Mps_title}]内容：{Gather_Content}\n")
        # 请求参数
        url = "https://mp.weixin.qq.com/cgi-bin/appmsg"
        count=5
        params = {
            "action": "list_ex",
            "begin": start_page,
            "count": count,
            "fakeid": faker_id,
            "type": "9",
            "token": self.token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1"
        }

        # 连接超时
        session=self.session
        # 起始页数
        i = start_page
        while True:
            if i >= MaxPage:
                break
            begin = i * count
            params["begin"] = str(begin)
            print(f"第{i+1}页开始爬取\n")
            # 随机暂停几秒，避免过快的请求导致过快的被查到
            time.sleep(random.randint(0,interval))
            try:
                headers = self.fix_header(url)
                resp = session.get(url, headers=headers, params = params, verify=False)
                
                msg = resp.json()

                self._cookies=resp.cookies
                # 流量控制了, 退出
                if msg['base_resp']['ret'] == 200013:
                    super().Error("frequencey control, stop at {}".format(str(begin)))
                    break
                
                if msg['base_resp']['ret'] == 200003:
                    super().Error("Invalid Session, stop at {}".format(str(begin)),code="Invalid Session")
                    break
                
                # 如果返回的内容中为空则结束
                if 'app_msg_list' not in msg:
                    super().Error("all ariticle parsed")
                    break
                if msg['base_resp']['ret'] != 0:
                    super().Error("错误原因:{}:代码:{}".format(msg['base_resp']['err_msg'],msg['base_resp']['ret']),code=msg['base_resp']['err_msg'])
                    break    
                if "app_msg_list" in msg:
                    for item in msg["app_msg_list"]:
                        time.sleep(random.randint(1,3))
                        # info = '"{}","{}","{}","{}"'.format(str(item["aid"]), item['title'], item['link'], str(item['create_time']))
                        if Gather_Content:
                            if not super().HasGathered(item["aid"]):
                                item["content"] = self.content_extract(item['link'])
                                super().Wait(3,10,tips=f"{item['title']} 采集完成")
                        else:
                            item["content"] = ""
                        item["id"] = item["aid"]
                        item["mp_id"] = Mps_id
                        if CallBack is not None:
                            super().FillBack(CallBack=CallBack,data=item,Ext_Data={"mp_title":Mps_title,"mp_id":Mps_id})
                    print(f"第{i+1}页爬取成功\n")
                # 翻页
                i += 1
            except requests.exceptions.Timeout:
                print("Request timed out")
                break
            except requests.exceptions.RequestException as e:
                print(f"Request error: {e}")
                break
            finally:
                super().Item_Over(item={"mps_id":Mps_id,"mps_title":Mps_title},CallBack=Item_Over_CallBack)
        # Do not move the cursor if rate limiting, timeout, session failure, or
        # another incomplete response stopped this crawl before all requested pages.
        if i >= MaxPage:
            super().CommitSync(Mps_id)
        super().Over(CallBack=Over_CallBack)
        pass