import sys
import asyncio

# Windows 需要使用 ProactorEventLoop 以支持 Playwright 子进程
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from core.config import cfg
if cfg.get("redis.server.enabled", False):
        from tools.redis_server import run_redis_server
        run_redis_server(config_path="config.yaml")
import uvicorn
from core.print import print_warning, print_info, print_success
import threading
from driver.auth import start_auth_service   
import os

if __name__ == '__main__':
    print("环境变量:")
    for k,v in os.environ.items():
        print(f"{k}={v}")
    if cfg.args.init=="True":
        import init_sys as init
        init.init()
    start_auth_service()
    # 启动级联同步服务（如果配置为子节点）
    cascade_service_started = False
    if cfg.get("cascade.enabled", False) and cfg.get("cascade.node_type") == "child":
        try:
            from jobs.cascade_sync import cascade_sync_service
            from jobs.cascade_task_dispatcher import start_child_task_worker
            import asyncio
            
            cascade_sync_service.initialize()
            if cascade_sync_service.sync_enabled:
                # 在后台线程启动同步服务
                def run_sync():
                    asyncio.run(cascade_sync_service.start_periodic_sync())
                
                sync_thread = threading.Thread(target=run_sync, daemon=True)
                sync_thread.start()
                
                # 启动子节点任务拉取器
                poll_interval = cfg.get("cascade.task_poll_interval", 30)
                
                def run_task_worker():
                    asyncio.run(start_child_task_worker(poll_interval=poll_interval))
                
                task_worker_thread = threading.Thread(target=run_task_worker, daemon=True)
                task_worker_thread.start()
                
                cascade_service_started = True
                print_success(f"级联同步服务已启动，任务拉取间隔: {poll_interval}秒")
        except Exception as e:
            print_warning(f"启动级联同步服务失败: {str(e)}")
    else:
        print_info("级联模式未启用或当前节点为父节点")
    
    if not cascade_service_started:
        print_info("启动网关定时调度服务")
        import asyncio
        from jobs.cascade_task_dispatcher import cascade_schedule_service
        cascade_schedule_service.start()

    if  cfg.args.job =="True" and cfg.get("server.enable_job",False):
        from jobs import start_job
        threading.Thread(target=start_job,daemon=False).start()
        print_success("已开启定时任务")
        # 微信读书 Cookie 每 2 小时自动续期（有效则续期、过期则跳过，独立于消息任务）
        try:
            from jobs.weread_renew import start_weread_renew
            start_weread_renew()
        except Exception as e:
            print_warning(f"启动微信读书 Cookie 自动续期任务失败: {e}")
    else:
        print_warning("未开启定时任务")
    
    if cfg.get("gather.content_auto_check",False):
        from jobs import start_fix_article
        start_fix_article()
        print_success("已开启自动修正文章任务")
    else:
        print_warning("未开启自动修正文章任务")
    
    # 启动文章统计定时刷新任务
    if cfg.get("server.article_stats_refresh_enabled", False):  # 默认关闭
        from jobs.mps import start_article_stats_refresh
        start_article_stats_refresh()
    else:
        print_warning("文章统计定时刷新任务未启用")
    
    print("启动服务器")
    AutoReload=cfg.get("server.auto_reload",False)
    thread=cfg.get("server.threads",1)
    reload_dirs = ["apis", "core", "driver", "jobs", "schemas", "tools", "views", "web_ui"]
    
    # Windows 上禁用 reload 模式，因为会导致事件循环问题
    if sys.platform == 'win32' and AutoReload:
        print_warning("Windows 平台上禁用 reload 模式以确保 Playwright 正常工作")
        AutoReload = False
    
    # Windows 上使用自定义配置确保 ProactorEventLoop
    if sys.platform == 'win32':
        # 使用 uvicorn 的 Config 和 Server 类来控制事件循环
        config = uvicorn.Config(
            "web:app",
            host="0.0.0.0",
            port=int(cfg.get("port", 8001)),
            reload=False,
            reload_dirs=reload_dirs,
            reload_excludes=['static', 'data', 'node_modules', '*.pnpm*'],
            workers=thread,
        )
        server = uvicorn.Server(config)
        
        # 确保使用 ProactorEventLoop
        if not isinstance(asyncio.get_event_loop(), asyncio.ProactorEventLoop):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        asyncio.run(server.serve())
    else:
        uvicorn.run("web:app", host="0.0.0.0", port=int(cfg.get("port",8001)),
                reload=AutoReload,
                reload_dirs=reload_dirs,
                reload_excludes=['static','data','node_modules','*.pnpm*'],
                workers=thread,
                )
    pass
