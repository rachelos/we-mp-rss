<div align=center>
<img src="static/logo.svg" alt="We-MP-RSS Logo" width="20%">
<h1>WeRSS - WeChat Official Account RSS Subscription Assistant</h1>

[![Python Version](https://img.shields.io/badge/python-3.13.1+-red.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

[中文](README.zh-CN.md)|[English](ReadMe.md)

Quick Start
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  ghcr.io/rachelos/we-mp-rss:latest
```
Visit http://<your-ip>:8001/ to get started

# Quick Upgrade 

```
docker stop we-mp-rss
docker rm we-mp-rss
docker pull ghcr.io/rachelos/we-mp-rss:latest
# If you added other parameters, please modify accordingly
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  ghcr.io/rachelos/we-mp-rss:latest
```

# Official Image
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  rachelos/we-mp-rss:latest
```
# Proxy Mirror for Faster Access (Faster access in China)
```
docker run -d  --name we-mp-rss  -p 8001:8001 -v ./data:/app/data  docker.1ms.run/rachelos/we-mp-rss:latest  
```

# Special Thanks (In no particular order)
cyChaos, 子健MeLift, 晨阳, 童总, 胜宇, 军亮, 余光, 一路向北, 水煮土豆丝, 人可, 须臾, 澄明, 五梭,Jarvis,三三,哈基米,苹果 


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
A tool for subscribing to and managing WeChat Official Account content, providing RSS subscription functionality.
</div>
<p align="center">
  <a href="https://github.com/DIYgod/sponsors">
    <img src="https://raw.githubusercontent.com/DIYgod/sponsors/main/sponsors.wide.svg" />
  </a>
</p>

## Features

- WeChat Official Account content scraping and parsing
- RSS feed generation
- User-friendly web management interface
- Scheduled automatic content updates
- Multiple database support (default SQLite, optional MySQL)
- Multiple scraping methods support
- Optional `weread_mp` collection mode for `MP_WXS_*` feeds ([configuration](docs/weread-mp.md))
- Multiple RSS client support
- Authorization expiration reminders
- Custom notification channels
- Custom RSS title, description, and cover
- Custom RSS pagination size
- Export to md/docx/pdf/json formats
- API interface and WebHook support
- HTML content filtering rules (global rules and MP-specific rules)
- Multi-theme support (13 themes: Default Purple, Blue, Green, Orange, Rose, Teal, Pink, Indigo, Violet, Coffee, Navy, Dark Mode, Sepia)
- Responsive pagination (PC: click navigation, Mobile: load more button)
- **Cascade System**: Parent-child node architecture with intelligent task distribution for scaling collection capabilities
- **Environment Exception Statistics**: Automatic tracking and statistics of environment exceptions when accessing WeChat articles
- **Headers and Cookies Authentication**: Support custom headers and cookies in message tasks for authenticated webhook calls
- **Configuration Cache**: Support Redis, Memcached, and memory caching for improved configuration read performance


# ❤️ Sponsorship
If you find We-MP-RSS helpful, feel free to buy me a beer!<br/>
<img src="docs/赞赏码.jpg" width=180/>
[Paypal](https://www.paypal.com/ncp/payment/PUA72WYLAV5KW)

## Screenshots
- Login Interface  
<img src="docs/登录.png" alt="Login" width="80%"/><br/>
- Main Interface  
<img src="docs/主界面.png" alt="Main Interface" width="80%"/><br/>
- QR Code Authorization  
<img src="docs/扫码授权.png" alt="QR Code Authorization" width="80%"/><br/>
- Add Subscription  
<img src="docs/添加订阅.png" alt="Add Subscription" width="80%"/><br/>

- Client Application<br/>
<img src="docs/folo.webp" alt="FOLO Client Application" width="80%"/><br/>



## System Architecture

The project adopts a front-end and back-end separation architecture:
- Backend: Python + FastAPI
- Frontend: Vue 3 + Vite
- Database: SQLite (default)/MySQL
<img src="docs/架构原理.png" alt="Architecture Diagram" width="80%"/>

For more project principles, please refer to the [Project Documentation](https://deepwiki.com/rachelos/we-mp-rss/3.5-notification-system).

## HTML Content Filtering Rules

WeRSS supports custom HTML content filtering rules to automatically clean unwanted elements during article content collection, such as ads, recommendation links, etc.

### Features

- **Global Rules**: Apply to all official accounts when no specific account is selected
- **MP-Specific Rules**: Configure different filtering rules for specific official accounts
- **Priority Control**: Set rule priority (higher number = executed first)
- **Multiple Filtering Methods**:
  - Remove elements by ID
  - Remove elements by CSS Class
  - Remove elements by CSS Selector
  - Filter elements by attribute
  - Remove content by regular expression
  - Remove common HTML elements (script, style, comments, etc.)

### Usage

1. Login to the admin interface, go to "Filter Rules" page
2. Click "Add Filter Rule"
3. Configure the rule:
   - **Select Official Account**: Optional, leave empty for global rules
   - **Rule Name**: A descriptive name for the rule
   - **Priority**: Higher number means higher priority (0-100)
   - **Filter Configuration**:
     - Remove ID elements: One ID per line, e.g., `ad-banner`
     - Remove Class elements: One class per line, e.g., `ad-container`
     - CSS Selectors: e.g., `div.ad-wrapper`, `.recommend-list > li`
     - Attribute filtering: e.g., `data-type="ad"`
     - Regular expressions: For precise content matching and removal

### API Endpoints

```bash
# Get filter rules list
GET /api/filter-rules

# Create filter rule
POST /api/filter-rules
{
  "mp_id": "[]",  // Empty array for global rules
  "rule_name": "Global Ad Filter",
  "remove_ids": ["ad-banner"],
  "remove_classes": ["ad-container"],
  "priority": 10
}

# Update filter rule
PUT /api/filter-rules/{rule_id}

# Delete filter rule
DELETE /api/filter-rules/{rule_id}
```

## Installation Guide

# Development
## Environment Requirements
- Python>=3.13.1
- Node>=20.18.3
### Backend Service

1. Clone the project
```bash
git clone https://github.com/rachelos/we-mp-rss.git
cd we-mp-rss
```

2. Install Python dependencies
```bash
pip install -r requirements.txt
```

3. Configure database
Copy and modify the configuration file:
```bash
cp config.example.yaml config.yaml
copy config.example.yaml config.yaml
```
3. Start the service
```bash
python main.py -job True -init True
```

## Frontend Development
1. Install frontend dependencies
```bash
cd we-mp-rss/web_ui
yarn install
```

2. Start frontend service
```bash
yarn dev
```
3. Access frontend page
```
http://localhost:3000
```

# Environment Variable Configuration

The following are the environment variable configurations supported in `config.yaml`:

| Environment Variable | Default Value | Description |
|----------|--------|------|
| `APP_NAME` | `we-mp-rss` | Application name |
| `SERVER_NAME` | `we-mp-rss` | Server name |
| `WEB_NAME` | `WeRSS微信公众号订阅助手` | Frontend display name |
| `SEND_CODE` | `False` | Whether to send authorization QR code in expired notification (text-only notification by default) |
| `CODE_TITLE` | `WeRSS授权二维码` | QR code notification title |
| `ENABLE_JOB` | `True` | Whether to enable scheduled tasks |
| `AUTO_RELOAD` | `False` | Auto-restart service on code changes |
| `THREADS` | `2` | Maximum number of threads |
| `DB` | `sqlite:///data/db.db` | Database connection string |
| `DINGDING_WEBHOOK` | Empty | DingTalk notification webhook URL |
| `WECHAT_WEBHOOK` | Empty | WeChat notification webhook URL |
| `FEISHU_WEBHOOK` | Empty | Feishu notification webhook URL |
| `CUSTOM_WEBHOOK` | Empty | Custom notification webhook URL |
| `SECRET_KEY` | `we-mp-rss` | Secret key |
| `USER_AGENT` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36/WeRss` | User agent |
| `SPAN_INTERVAL` | `10` | Scheduled task execution interval (seconds) |
| `WEBHOOK.CONTENT_FORMAT` | `html` | Article content sending format |
| `PORT` | `8001` | API service port |
| `DEBUG` | `False` | Debug mode |
| `MAX_PAGE` | `5` | Maximum scraping pages |
| `RSS_BASE_URL` | Empty | RSS domain address |
| `RSS_LOCAL` | `False` | Whether to use local RSS links |
| `RSS_TITLE` | Empty | RSS title |
| `RSS_DESCRIPTION` | Empty | RSS description |
| `RSS_COVER` | Empty | RSS cover |
| `RSS_FULL_CONTEXT` | `True` | Whether to display full text |
| `RSS_ADD_COVER` | `True` | Whether to add cover images |
| `RSS_CDATA` | `False` | Whether to enable CDATA |
| `RSS_PAGE_SIZE` | `30` | RSS pagination size |
| `TOKEN_EXPIRE_MINUTES` | `4320` | Login session validity duration (minutes) |
| `CACHE.DIR` | `./data/cache` | Cache directory |
| `ARTICLE.TRUE_DELETE` | `False` | Whether to truly delete articles |
| `GATHER.CONTENT` | `True` | Whether to collect content |
| `GATHER.MODEL` | `app` | Collection mode |
| `GATHER.CONTENT_AUTO_CHECK` | `False` | Whether to automatically check uncollected article content |
| `GATHER.CONTENT_AUTO_INTERVAL` | `59` | Time interval for automatically checking uncollected article content (minutes) |
| `GATHER.CONTENT_MODE` | `web` | Content correction mode |
| `SAFE_HIDE_CONFIG` | `db,secret,token,notice.wechat,notice.feishu,notice.dingding` | Configuration information to hide |
| `SAFE_LIC_KEY` | `RACHELOS` | Authorization encryption key |
| `LOG_FILE` | Empty | Log file path |
| `LOG_LEVEL` | `INFO` | Log level |
| `EXPORT_PDF` | `False` | Whether to enable PDF export functionality |


