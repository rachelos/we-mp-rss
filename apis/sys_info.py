import os
import platform
import sqlite3
import sys
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from core.auth import get_current_user, get_current_user_or_ak
from .base import success_response, error_response
from core.config import cfg
from jobs.mps import TaskQueue
from driver.success import getLoginInfo,getStatus
router = APIRouter(prefix="/sys", tags=["系统信息"])
def get_docker_version():
        try:
            with open("./docker_version.txt", "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            return "未知"
# 记录服务器启动时间
_START_TIME = time.time()
@router.get("/base_info", summary="常规信息")
async def get_base_info() -> Dict[str, Any]:
    try:
        from .ver import API_VERSION
        from core.config import VERSION as CORE_VERSION,LATEST_VERSION
       
        base_info = {
            'api_version': API_VERSION,
            'docker_version': get_docker_version(),
            'core_version': CORE_VERSION,
            "ui":{
                "name": cfg.get("server.name",""),
                "web_name": cfg.get("server.web_name","WeRss公众号订阅平台"),
            }
        }
        return success_response(data=base_info)
    except Exception as e:
        return error_response(
            code=50001,
            message=f"获取信息失败: {str(e)}"
        )    
    

from core.resource import get_system_resources
from tools.storage_maintenance import (
    create_consistent_sqlite_backup,
    gzip_file_chunks,
    resolve_sqlite_path,
)

@router.get("/resources", summary="获取系统资源使用情况")
async def system_resources(
    current_user: dict = Depends(get_current_user_or_ak)
) -> Dict[str, Any]:
    """获取系统资源使用情况
    
    Returns:
        BaseResponse格式的资源使用信息，包括:
        - cpu: CPU使用率(%)
        - memory: 内存使用情况
        - disk: 磁盘使用情况
    """
    try:
        resources_info=get_system_resources()
        resources_info["queue"]=TaskQueue.get_queue_info(),
        return success_response(data=resources_info)
    except Exception as e:
        return error_response(
            code=50002,
            message=f"获取系统资源失败: {str(e)}"
        )


@router.get("/storage/backup", summary="下载 SQLite 一致性备份")
def download_storage_backup(
    current_user: dict = Depends(get_current_user),
):
    if os.getenv("WERSS_STORAGE_BACKUP_ENABLED", "").lower() != "true":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    database_url = os.getenv("DB", "sqlite:///./data/db.db")
    try:
        backup_path, metadata = create_consistent_sqlite_backup(
            resolve_sqlite_path(database_url)
        )
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create SQLite backup: {exc}",
        ) from exc

    headers = {
        "Content-Disposition": 'attachment; filename="werss-production.sqlite.gz"',
        "X-SQLite-Integrity": metadata["integrity"],
        "X-SQLite-Bytes": str(metadata["file_bytes"]),
    }
    return StreamingResponse(
        gzip_file_chunks(backup_path, remove_parent_on_close=True),
        media_type="application/gzip",
        headers=headers,
    )
from core.article_lax import get_article_info, refresh_article_info
from .ver import API_VERSION
from core.base import VERSION as CORE_VERSION,LATEST_VERSION

@router.post("/article/refresh", summary="手动刷新文章统计")
async def refresh_article_stats(
    current_user: dict = Depends(get_current_user_or_ak)
) -> Dict[str, Any]:
    """手动刷新文章统计信息
    
    Returns:
        BaseResponse格式的刷新结果
    """
    try:
        refresh_article_info()
        return success_response(message="文章统计刷新任务已启动")
    except Exception as e:
        return error_response(
            code=50003,
            message=f"刷新文章统计失败: {str(e)}"
        )

@router.get("/info", summary="获取系统信息")
async def get_system_info(
    current_user: dict = Depends(get_current_user_or_ak)
) -> Dict[str, Any]:
    """获取当前系统的各种信息
    
    Returns:
        BaseResponse格式的系统信息，包括:
        - os: 操作系统信息
        - python_version: Python版本
        - uptime: 服务器运行时间(秒)
        - system: 系统详细信息
    """
    try:
      
        from driver.token import get as get_val
        # 获取系统信息
        system_info = {
            'os': {
                'name': platform.system(),
                'version': platform.version(),
                'docker_version': get_docker_version(),
                'release': platform.release(),
            },
            'python_version': sys.version,
            'uptime': round(time.time() - _START_TIME, 2),
            'system': {
                'node': platform.node(),
                'machine': platform.machine(),
                'processor': platform.processor(),
            },
            'api_version': API_VERSION,
            'core_version': CORE_VERSION,
            'latest_version':LATEST_VERSION,
            'need_update':CORE_VERSION != LATEST_VERSION,
            "wx":{
                'token':get_val('token',''),
                'expiry_time':get_val('expiry.expiry_time','') if getStatus() else "",
                "info":getLoginInfo(),
                "login":getStatus(),
            },
            "article":get_article_info(),
            'queue':TaskQueue.get_queue_info(),
        }
        return success_response(data=system_info)
    except Exception as e:
        return error_response(
            code=50001,
            message=f"获取系统信息失败: {str(e)}"
        )
