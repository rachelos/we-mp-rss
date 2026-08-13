<div align=center>
<img src="static/logo.svg" alt="We-MP-RSS Logo" width="20%">
<h1>WeRSS - 微信公众号订阅助手</h1>

[![Python Version](https://img.shields.io/badge/python-3.13.1+-red.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

[中文](README.zh-CN.md)|[English](ReadMe.md)

快速运行
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  ghcr.io/rachelos/we-mp-rss:latest
```
http://<您的ip>:8001/  即可开启

# 快速升级 

```
docker stop we-mp-rss
docker rm we-mp-rss
docker pull ghcr.io/rachelos/we-mp-rss:latest
# 如果添加了其它参数，请自行修改
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  ghcr.io/rachelos/we-mp-rss:latest
```

# 官方镜像
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  rachelos/we-mp-rss:latest
```
# 代理镜像加速访问（国内访问速度更快）
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  docker.1ms.run/rachelos/we-mp-rss:latest  
```

# 感谢伙伴(排名不分先后)
 cyChaos、 子健MeLift、 晨阳、 童总、 胜宇、 军亮、 余光、 一路向北、 水煮土豆丝、 人可、 须臾、 澄明
、五梭




 <br/>
 <img src="https://github.com/user-attachments/assets/cbe924f2-d8b0-48b0-814e-7c06ccb1911c" height="60" />
    <img src="https://github.com/user-attachments/assets/6997a236-3df3-49d5-98a4-514f6d1a02c4" height="60" />
    <br />
    <br />
    <a href="https://github.com/RSSNext/Folo/stargazers"><img src="https://img.shields.io/github/stars/RSSNext/Follow?color=ffcb47&labelColor=black&style=flat-square&logo=github&label=Stars" /></a>
    <a href="https://github.com/RSSNext/Folo/graphs/contributors"><img src="https://img.shields.io/github/contributors/RSSNext/Folo?style=flat-square&logo=github&label=Contributors&labelColor=black" /></a>
    <a href="https://status.follow.is/" target="_blank"><img src="https://status.follow.is/api/badge/18/uptime?color=%2344CC10&labelColor=black&style=flat-square"/></a>
    <a href="https://github.com/RSSNext/Folo/releases"><img src="https://img.shields.io/github/downloads/RSSNext/Folo/total?color=369eff&labelColor=black&logo=github&style=flat-square&label=Downloads" /></a>
    <a href="https://x.com/intent/follow?screen_name=folo_is"><img src="https://img.shields.io/badge/Follow-blue?color=1d9bf0&logo=x&labelColor=black&style=flat-square" /></a>
    <a href="https://discord.gg/followapp" target="_blank"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fdiscord.com%2Fapi%2Finvites%2Ffollowapp%3Fwith_counts%3Dtrue&query=approximate_member_count&color=5865F2&label=Discord&labelColor=black&logo=discord&logoColor=white&style=flat-square"/></a>
    <br />
一个用于订阅和管理微信公众号内容的工具，提供RSS订阅功能。
</div>
<p align="center">
  <a href="https://github.com/DIYgod/sponsors">
    <img src="https://raw.githubusercontent.com/DIYgod/sponsors/main/sponsors.wide.svg" />
  </a>
</p>

## 功能特性

- 微信公众号内容抓取和解析
- RSS订阅生成
- 用户友好的Web管理界面
- 定时自动更新内容
- 支持多种数据库（默认SQLite，可选MySQL）
- 支持多种抓取方式
- 可选 `weread_mp` 模式采集现有 `MP_WXS_*` 公众号（[配置说明](docs/weread-mp.md)）
- 支持多种RSS客户端
- 支持授权过期提醒
- 支持自定义通知渠道
- 支持自定义RSS标题、描述、封面
- 支持自定义RSS分页大小
- 支持导出md/docx/pdf/json格式
- 支持API接口调用/WebHook调用
- 支持HTML内容过滤规则（全局规则和公众号专属规则）
- 支持多主题切换（13种主题：默认紫色、清新蓝色、自然绿色、活力橙色、玫瑰红、青碧色、樱花粉、靛青色、紫罗兰、咖啡棕、深海蓝、深色模式、护眼模式）
- 支持响应式分页（PC端点击翻页，移动端加载更多按钮）
- **级联系统**：支持父子节点架构，智能任务分发，扩展采集能力
- **环境异常统计**：自动统计微信公众号文章获取时的环境异常情况
- **Headers和Cookies认证**：消息任务支持自定义Headers和Cookies，用于需要认证的WebHook调用
- **配置缓存**：支持Redis、Memcached和内存缓存，提升配置读取性能


# ❤️ 赞助
如果觉得 We-MP-RSS 对你有帮助，欢迎给我来一杯啤酒！<br/>
<img src="docs/赞赏码.jpg" width=180/>
[Paypal](https://www.paypal.com/ncp/payment/PUA72WYLAV5KW)

## 界面截图
- 登录界面  
<img src="docs/登录.png" alt="登录" width="80%"/><br/>
- 主界面  
<img src="docs/主界面.png" alt="主界面" width="80%"/><br/>
- 扫码授权  
<img src="docs/扫码授权.png" alt="扫码授权" width="80%"/><br/>
- 添加订阅  
<img src="docs/添加订阅.png" alt="添加订阅" width="80%"/><br/>

- 客户端应用<br/>
<img src="docs/folo.webp" alt="FOLO客户端应用" width="80%"/><br/>



## 系统架构

项目采用前后端分离架构：
- 后端：Python + FastAPI
- 前端：Vue 3 + Vite
- 数据库：SQLite (默认)/MySQL
<img src="docs/架构原理.png" alt="架构原理" width="80%"/>

更多项目原理，请参考[项目文档](https://deepwiki.com/rachelos/we-mp-rss/3.5-notification-system)。

## 安装指南

# 二次开发
## 环境需求
- Python>=3.13.1
- Node>=20.18.3
### 后端服务

1. 克隆项目
```bash
git clone https://github.com/rachelos/we-mp-rss.git
cd we-mp-rss
```

2. 安装Python依赖
```bash
pip install -r requirements.txt
```

3. 配置数据库
复制并修改配置文件：
```bash
cp config.example.yaml config.yaml
copy config.example.yaml config.yaml
```
3. 启动服务
```bash
python main.py -job True -init True
```

## 前端开发
1. 安装前端依赖
```bash
cd we-mp-rss/web_ui
yarn install
```

2. 启动前端服务
```bash
yarn dev
```
3. 访问前端页面
```
http://localhost:3000
```

# 环境变量配置

以下是 `config.yaml` 中支持的环境变量配置：

| 环境变量 | 默认值 | 描述 |
|----------|--------|------|
| `APP_NAME` | `we-mp-rss` | 应用名称 |
| `SERVER_NAME` | `we-mp-rss` | 服务名称 |
| `WEB_NAME` | `WeRSS微信公众号订阅助手` | 前端显示名称 |
| `WERSS_AUTH_WEB` | `False` | 通过web方式授权 |
| `BROWSER_TYPE` | `firefox` | 浏览器类型默认firefox |
| `SEND_CODE` | `False` | 过期通知中是否附带授权二维码（默认仅发送文字通知） |
| `CODE_TITLE` | `WeRSS授权二维码` | 二维码通知标题 |
| `ENABLE_JOB` | `True` | 是否启用定时任务 |
| `AUTO_RELOAD` | `False` | 代码修改自动重启服务 |
| `THREADS` | `2` | 最大线程数 |
| `DB` | `sqlite:///data/db.db` | 数据库连接字符串 |
| `DINGDING_WEBHOOK` | 空 | 钉钉通知Webhook地址 |
| `WECHAT_WEBHOOK` | 空 | 微信通知Webhook地址 |
| `FEISHU_WEBHOOK` | 空 | 飞书通知Webhook地址 |
| `CUSTOM_WEBHOOK` | 空 | 自定义通知Webhook地址 |
| `SECRET_KEY` | `we-mp-rss` | 密钥 |
| `USER_AGENT` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36/WeRss` | 用户代理 |
| `SPAN_INTERVAL` | `10` | 定时任务执行间隔（秒） |
| `WEBHOOK.CONTENT_FORMAT` | `html` | 文章内容发送格式 |
| `PORT` | `8001` | API服务端口 |
| `DEBUG` | `False` | 调试模式 |
| `MAX_PAGE` | `5` | 最大采集页数 |
| `RSS_BASE_URL` | 空 | RSS域名地址 |
| `RSS_LOCAL` | `False` | 是否为本地RSS链接 |
| `RSS_TITLE` | 空 | RSS标题 |
| `RSS_DESCRIPTION` | 空 | RSS描述 |
| `RSS_COVER` | 空 | RSS封面 |
| `RSS_FULL_CONTEXT` | `True` | 是否显示全文 |
| `RSS_ADD_COVER` | `True` | 是否添加封面图片 |
| `RSS_CDATA` | `False` | 是否启用CDATA |
| `RSS_PAGE_SIZE` | `30` | RSS分页大小 |
| `TOKEN_EXPIRE_MINUTES` | `4320` | 登录会话有效时长（分钟） |
| `CACHE.DIR` | `./data/cache` | 缓存目录 |
| `ARTICLE.TRUE_DELETE` | `False` | 是否真实删除文章 |
| `GATHER.CONTENT` | `True` | 是否采集内容 |
| `GATHER.MODEL` | `app` | 采集模式 |
| `GATHER.CONTENT_AUTO_CHECK` | `False` | 是否自动检查未采集文章内容 |
| `GATHER.CONTENT_AUTO_INTERVAL` | `59` | 自动检查未采集文章内容的时间间隔（分钟） |
| `GATHER.CONTENT_MODE` | `web` | 内容修正模式 |
| `SAFE_HIDE_CONFIG` | `db,secret,token,notice.wechat,notice.feishu,notice.dingding` | 需要隐藏的配置信息 |
| `SAFE_LIC_KEY` | `RACHELOS` | 授权加密KEY |
| `LOG_FILE` | 空 | 日志文件路径 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `EXPORT_PDF` | `False` | 是否启用PDF导出功能 |
| `EXPORT_PDF_DIR` | `./data/pdf` | PDF导出目录 |
| `EXPORT_MARKDOWN` | `False` | 是否启用markdown导出功能 |
| `EXPORT_MARKDOWN_DIR` | `./data/markdown` | markdown导出目录 |

# 使用说明

1. 启动服务后，访问 `http://<您的IP>:8001` 进入管理界面。
2. 使用微信扫码授权后，即可添加和管理订阅。
3. 定时任务会自动更新内容，并生成RSS订阅链接。

## Access Key 认证

WeRSS 支持使用 Access Key (AK) 进行 API 认证，适用于程序化访问和自动化脚本。

### 创建 Access Key

1. 登录 WeRSS 管理界面
2. 进入"Access Key 管理"页面
3. 点击"创建 Access Key"按钮
4. 填写名称、描述、权限和过期时间
5. 创建成功后，妥善保存 Access Key 和 Secret Key（Secret Key 只显示一次）

### 使用 Access Key 调用 API

在请求头中添加 `Authorization` 字段，格式为 `AK-SK {access_key}:{secret_key}`：

```bash
curl -H "Authorization: AK-SK your_access_key:your_secret_key" \
     http://localhost:8001/api/feeds
```

#### Python 示例

```python
import requests

access_key = "your_access_key"
secret_key = "your_secret_key"
base_url = "http://localhost:8001"

headers = {
    "Authorization": f"AK-SK {access_key}:{secret_key}"
}

# 获取订阅列表
response = requests.get(f"{base_url}/api/feeds", headers=headers)
print(response.json())
```

#### JavaScript 示例

```javascript
const accessKey = "your_access_key";
const secretKey = "your_secret_key";
const baseUrl = "http://localhost:8001";

const headers = {
  "Authorization": `AK-SK ${accessKey}:${secretKey}`
};

// 获取订阅列表
fetch(`${baseUrl}/api/feeds`, { headers })
  .then(res => res.json())
  .then(data => console.log(data));
```

详细文档请参考：[AK 认证指南](docs/AK_Authentication_Guide.md)

## HTML 内容过滤规则

WeRSS 支持自定义 HTML 内容过滤规则，可以在采集文章内容时自动清理不需要的元素，如广告、推荐链接等。

### 功能特点

- **全局规则**：不指定公众号时，规则对所有公众号生效
- **公众号专属规则**：可以为特定公众号或多个公众号配置不同的过滤规则
- **优先级控制**：支持设置规则优先级，数值越大越先执行
- **多种过滤方式**：
  - 按 ID 移除元素
  - 按 CSS Class 移除元素
  - 按 CSS 选择器移除元素
  - 按属性过滤元素
  - 按正则表达式移除内容
  - 移除常见 HTML 元素（script、style、注释等）

### 使用方法

1. 登录管理界面，进入「过滤规则」页面
2. 点击「添加过滤规则」
3. 配置规则：
   - **选择公众号**：可选多个公众号，不选择则为全局规则
   - **规则名称**：便于识别的规则名称
   - **优先级**：数值越大优先级越高（0-100）
   - **过滤配置**：
     - 移除 ID 元素：每行一个 ID，如 `ad-banner`
     - 移除 Class 元素：每行一个 class，如 `ad-container`
     - CSS 选择器：如 `div.ad-wrapper`、`.recommend-list > li`
     - 属性过滤：如 `data-type="ad"`
     - 正则表达式：用于精确匹配和移除内容

### 示例配置

#### 全局广告过滤规则
```
规则名称：全局广告清理
公众号：不选择（全局规则）
优先级：10
移除 ID：ad-banner、footer-nav
移除 Class：ad-container、recommend-box
CSS 选择器：div.ad-wrapper、.recommend-list > li
移除常见 HTML 元素：开启
```

#### 特定公众号规则
```
规则名称：某公众号专属过滤
公众号：选择特定公众号
优先级：20（高于全局规则，会先执行）
移除 Class：custom-ad、special-banner
```

### API 接口

过滤规则支持完整的 REST API 操作：

```bash
# 获取过滤规则列表
GET /api/filter-rules

# 创建过滤规则
POST /api/filter-rules
{
  "mp_id": "[]",  // 空数组表示全局规则
  "rule_name": "全局广告过滤",
  "remove_ids": ["ad-banner"],
  "remove_classes": ["ad-container"],
  "priority": 10
}

# 更新过滤规则
PUT /api/filter-rules/{rule_id}

# 删除过滤规则
DELETE /api/filter-rules/{rule_id}
```

# 常见问题

- **如何修改数据库连接？**
  在 `config.yaml` 中修改 `db` 配置项，或通过环境变量 `DB` 覆盖。

- **如何启用钉钉通知？**
  在 `config.yaml` 中填写 `notice.dingding` 或通过环境变量 `DINGDING_WEBHOOK` 设置。

- **如何调整定时任务间隔？**
  修改 `config.yaml` 中的 `interval` 或通过环境变量 `SPAN_INTERVAL` 设置。

- **如何开启定时任务？**
  1、修改 `config.yaml` 中的 `ENABLE_JOB` 或通过环境变量 `ENABLE_JOB` 设置 为True。
  2、在UI界面的消息任务中，添加定时任务。
  
- **如何修改文章内容发送格式？**
  修改 `config.yaml` 中的 `WEBHOOK.CONTENT_FORMAT` 或通过环境变量 `WEBHOOK.CONTENT_FORMAT` 设置。

- **默认帐号、密码是多少？**
  - 默认帐号：admin
  - 默认密码：admin@123

- **数据库连接串示例**
  - 调整环境变量DB为您的数据库连接字符串。
  - SQLite 连接示例: 
  ```
  sqlite:///data/db.db
  ```
  - PostgreSQL 连接示例: 
  ```
  postgresql://<username>:<password>@<host>/<database>
  ```
  - MySQL 连接示例:
  ```
  mysql+pymysql://<username>:<password>@<host>/<database>?charset=utf8mb4
  ```


[Star History Chart]: https://api.star-history.com/svg?repos=rachelos/we-mp-rss&type=Timeline
