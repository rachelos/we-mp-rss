<div align=center>
<img src="static/logo.svg" alt="We-MP-RSS Logo" width="20%">
<h1>WeRSS - 微信公众号订阅助手</h1>

[![Python Version](https://img.shields.io/badge/python-3.13.1+-red.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

快速运行
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  ghcr.io/rachelos/we-mp-rss:latest
```
http://<您的ip>:8001/  即可开启

# 官方镜像
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  rachelos/we-mp-rss:latest
```
# 代理镜像加速访问（国内访问速度更快）
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  docker.1ms.run/rachelos/we-mp-rss:latest  docker.1ms.run/rachelos/we-mp-rss:latest
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
- 支持多种RSS客户端
- 支持授权过期提醒


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
| `SEND_CODE` | `True` | 是否发送授权二维码通知 |
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
| `PAGE_LIMIT` | `1` | 最大更新页数 |
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
