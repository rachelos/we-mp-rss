import os
import sqlite3
from pathlib import Path

import psutil

from tools.storage_maintenance import resolve_sqlite_path, storage_report

# Desc: 资源信息
# Date: 2021-04-29 15:59
# Author: Rachel
# 缓存不会频繁变动的系统信息
_STATIC_INFO = {
    'cpu': {
        'cores': psutil.cpu_count(logical=False),
        'threads': psutil.cpu_count(logical=True)
    },
    'memory': {
        'total': round(psutil.virtual_memory().total / (1024 ** 3), 2)
    },
    'disk': {
        'total': round(psutil.disk_usage('./').total / (1024 ** 3), 2)
    }
}

def get_system_resources():
    # 获取动态变化的资源信息
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.1)
    disk = psutil.disk_usage('./')
    # 获取当前 Python 进程的资源占用情况
    current_process = psutil.Process()
    process_cpu_percent = current_process.cpu_percent(interval=0.1)
    process_mem_info = current_process.memory_info()
    # 单位转换函数
    def to_gb(bytes_value):
            return round(bytes_value / (1024 ** 3), 2)
        
    database_url = os.getenv("DB", "sqlite:///./data/db.db")
    data_dir = Path(os.getenv("WERSS_DATA_DIR", "./data"))
    try:
        persistent_storage = storage_report(
            data_dir.resolve(),
            resolve_sqlite_path(database_url),
        )
    except (OSError, ValueError, sqlite3.Error):
        persistent_storage = {
            "path": str(data_dir),
            "available": False,
        }

    resources_info = {
            'cpu': {
                'percent': cpu_percent,
                'cores': _STATIC_INFO['cpu']['cores'],
                'threads': _STATIC_INFO['cpu']['threads']
            },
            'memory': {
                'total': _STATIC_INFO['memory']['total'],
                'used': to_gb(mem.used),
                'free': to_gb(mem.free),
                'percent': mem.percent
            },
            'disk': {
                'total': _STATIC_INFO['disk']['total'],
                'used': to_gb(disk.used),
                'free': to_gb(disk.free),
                'percent': disk.percent
            },
            'process': {
                'cpu_percent': process_cpu_percent,
                'memory_used': to_gb(process_mem_info.rss),
                'memory_percent': current_process.memory_percent()
            },
            'persistent_storage': persistent_storage,
        }
    return resources_info
