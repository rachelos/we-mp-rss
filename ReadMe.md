<div align=center>
<img src="static/logo.svg" alt="We-MP-RSS Logo" width="20%">
<h1>WeRSS - 微信公众号订阅助手</h1>

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

快速运行
```
docker run -d  --name we-mp-rss  -p 8001:8001   ghcr.io/rachelos/we-mp-rss:latest
```
http://<您的ip>:8001/  即可开启

# 官方镜像和代理镜像
```
docker run -d  --name we-mp-rss  -p 8001:8001   rachelos/we-mp-rss:latest
docker run -d  --name we-mp-rss  -p 8001:8001   docker.1ms.run/rachelos/we-mp-rss:latest
```
</div>

一个用于订阅和管理微信公众号内容的工具，提供RSS订阅功能。

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

## 界面截图
- 登录界面  
<img src="docs/登录.png" alt="登录" width="80%"/><br/>
- 主界面  
<img src="docs/主界面.png" alt="主界面" width="80%"/><br/>

- 添加订阅  
<img src="docs/添加订阅.png" alt="添加订阅" width="80%"/><br/>

- 扫码授权  
<img src="docs/扫码授权.png" alt="扫码授权" width="80%"/><br/>
## 系统架构

项目采用前后端分离架构：
- 后端：Python + FastAPI
- 前端：Vue 3 + Vite
- 数据库：SQLite (默认)/MySQL

## 安装指南

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

4. 启动API服务
```bash
python3 init_sys.py
uvicorn web:app --host 0.0.0.0 --port 8001 --reload
```
或
```bash
sh start.sh
```

### 前端界面

1. 进入web_ui目录
```bash
cd web_ui
```

2. 安装Node.js依赖
```bash
npm install
```

3. 启动开发服务器
```bash
npm run dev
```

## 定时任务

配置定时抓取微信公众号内容：
```bash
python job.py

```

## 配置说明

编辑`config.yaml`文件配置以下参数：
- 数据库连接
- 微信公众号配置
- 抓取间隔时间
- API密钥等

## API文档

API服务启动后，访问以下地址查看文档：
- Swagger UI: http://localhost:8001/api/docs

## ⚙️ 环境变量
[更多环境变量配置请查看`config.example.yaml`文件](config.example.yaml)
| 变量名                   | 说明                                                                          | 默认值                      |
| ------------------------ | ---------------------------------------------------------------------------- | --------------------------- |
| `DB`                     | **必填** 数据库地址 例如: mysql+pymysql://<用户名>:<密码>@<数据库IP>/<数据库名>  | sqlite:///data/db.db        |
| `INTERVAL`               | 抓取间隔时间，单位秒                                                           | `10`                        |          
| `SECRET_KEY`             | JWT授权加密KEY                                                                | 'we-mp-rss'                 |
| `DINGDING_WEBHOOK`       | 钉钉机器人Webhook地址                                                          | -                           |
| `WECHAT_WEBHOOK`         | 微信机器人Webhook地址                                                          | -                           |
| `FEISHU_WEBHOOK`         | 飞书机器人Webhook地址                                                          | -                           |
| `MODEL`                  | 采集方式：web 或 api                                                          | web                         |
| `PORT`                   | API服务端口                                                                   | 8001                        |
| `DEBUG`                  | 调试模式                                                                      | False                       |
| `MAX_PAGE`               | 第一次添加时采集的最大页数                                                      | 5                           |
| `RSS_BASE_URL`           | RSS域名地址                                                                   | ""                          |
| `RSS_LOCAL`              | 是否为本地RSS链接                                                             | False                        |
| `TOKEN_EXPIRE_MINUTES`   | 登录会话有效时长(分钟)                                                         | 60                          |
| `GATHER.CONTENT`         | 是否采集内容                                                                  | True                        |
| `GATHER.MODEL`           | 采集模式(web模式可采集发布链接，api模式可采集临时链接)                           | web                         |
| `LOG_FILE`               | 日志文件路径，默认为空字符串，表示不输出到文件。如果要输出到文件，可以指定一个路径如：/var/log/we-mp-rss.log | -                           |
| `LOG_LEVEL`              | 日志级别(DEBUG, INFO, WARNING, ERROR, CRITICAL)                              | INFO                        |
| `RSS_FULL_CONTEXT`       | 是否显示全文                                                                | False                       |




## 快速运行
### Docker Sqlite
```
docker run -d \
  --name we-mp-rss \
  -p 8001:8001 \
  -e DB=sqlite:///data/db.db \
  -e USERNAME:admin \
  -e PASSWORD:admin@123 \
  -e DINGDING_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx \
  -v $(pwd)/data:/app/data \
  ghcr.io/rachelos/we-mp-rss:latest

```
### Docker Mysql
```
docker run -d \
  --name we-mp-rss \
  -p 8001:8001 \
  -e DB=mysql+pymysql://<username>:<password>@<host>/<database>?charset=utf8mb4 \
  -e USERNAME:admin \
  -e PASSWORD:admin@123 \
  -e DINGDING_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx \
  -v $(pwd)/data:/app/data \
  ghcr.io/rachelos/we-mp-rss:latest
```

# Docker构建及运行
```
# 构建
docker build -t we-mp-rss .
# Docker运行
docker run -d --name we-mp-rss -p 8001:8001 we-mp-rss
```

## 开发指南

### 后端开发
1. 安装开发依赖
```bash
pip install -r requirements-dev.txt
```

2. 运行测试
```bash
pytest
```

### 前端开发
1. 修改环境变量
编辑`.env.development`文件

2. 开发模式
```bash
npm run dev
```

3. 构建生产版本
```bash
npm run build
```




## 贡献指南

欢迎提交Pull Request。在提交前请确保：
1. 代码通过所有测试
2. 更新相关文档
3. 遵循代码风格指南
# 仓库地址
- [GitHub：](https://github.com/rachelos/we-mp-rss)https://github.com/rachelos/we-mp-rss
- [Gitee：](https://gitee.com/rachel_os/we-mp-rss)https://gitee.com/rachel_os/we-mp-rss

# 分享交流群
QQ:244538330

# 友情链接
[WeWe RSS](https://github.com/cooderl/wewe-rss)


# ❤️ 赞助
如果觉得 We-MP-RSS 对你有帮助，欢迎给我来一杯啤酒！<br/>
<img src="docs/赞赏码.jpg" width=180/>
[Paypal](https://www.paypal.com/ncp/payment/PUA72WYLAV5KW)


## 许可证

MIT License