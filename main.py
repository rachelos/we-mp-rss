import uvicorn
from core.config import cfg
import threading
import os
if __name__ == '__main__':
    if cfg.args.init=="True":
        import init_sys as init
        init.init()
    if  cfg.args.job =="True":
        from jobs import start_job
        threading.Thread(target=start_job,daemon=True).start()
    print("启动服务器")
    uvicorn.run("web:app", host="0.0.0.0", port=int(cfg.get("port",8001)), reload=True,reload_excludes=['static','web_ui'])
    pass