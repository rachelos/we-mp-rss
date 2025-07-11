import json
import requests
import time
import random
import yaml
import re
from bs4 import BeautifulSoup
from .base import WxGather
from core.log import logger
# 继承 BaseGather 类
class MpsApi(WxGather):

    # 重写 content_extract 方法
    def content_extract(self,  url):
        try:
            session=self.session
            r = session.get(url, headers=self.headers)
            if r.status_code == 200:
                text = r.text
                if text is None:
                    return
                soup = BeautifulSoup(text, 'html.parser')
                # 找到内容
                js_content_div = soup.find('div', {'id': 'js_content'})
                # 移除style属性中的visibility: hidden;
                if js_content_div is None:
                    return
                js_content_div.attrs.pop('style', None)
                # 找到所有的img标签
                img_tags = js_content_div.find_all('img')
                # 遍历每个img标签并修改属性，设置宽度为1080p
                for img_tag in img_tags:
                    if 'data-src' in img_tag.attrs:
                        img_tag['src'] = img_tag['data-src']
                        del img_tag['data-src']
                    if 'style' in img_tag.attrs:
                        style = img_tag['style']
                        # 使用正则表达式替换width属性
                        style = re.sub(r'width\s*:\s*\d+\s*px', 'width: 1080px', style)
                        img_tag['style'] = style
                return  js_content_div.prettify()
        except Exception as e:
                logger.error(e)
        return ""
    # 重写 get_Articles 方法
    def get_Articles(self, faker_id:str=None,Mps_id:str=None,Mps_title="",CallBack=None,start_page=0,MaxPage:int=1,interval=10,Gather_Content=True,Item_Over_CallBack=None,Over_CallBack=None):
        super().Start(mp_id=Mps_id)
        if self.Gather_Content:
             Gather_Content=True
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
                resp = session.get(url, headers=self.headers, params = params, verify=False)
                
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
                    super().Error("错误原因:{}:代码:{}".format(msg['base_resp']['err_msg'],msg['base_resp']['ret']),code="Invalid Session")
                    break    
                if "app_msg_list" in msg:
                    for item in msg["app_msg_list"]:
                        time.sleep(random.randint(1,3))
                        # info = '"{}","{}","{}","{}"'.format(str(item["aid"]), item['title'], item['link'], str(item['create_time']))
                        if Gather_Content:
                            item["content"] = self.content_extract(item['link'])
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
                super().Item_Over(item={Mps_id:Mps_id,Mps_title:Mps_title},CallBack=Item_Over_CallBack)
        super().Over(CallBack=Over_CallBack)
        pass