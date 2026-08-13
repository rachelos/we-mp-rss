"""
切换公众号账号后台任务管理。

职责：
1. 接收前端触发，立即返回 job_id（避免阻塞 HTTP 请求）。
2. 在后台线程跑实际的 Playwright 切换流程。
3. 维护每个 job 的状态（stage / message / finished / ok）。
4. 通过 asyncio.Queue 在 SSE 端点上广播进度事件。
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 全局单例
_MANAGER: Optional["SwitchJobManager"] = None
_LOCK = threading.Lock()


def get_manager() -> "SwitchJobManager":
    """进程内唯一 SwitchJobManager 实例。"""
    global _MANAGER
    if _MANAGER is None:
        with _LOCK:
            if _MANAGER is None:
                _MANAGER = SwitchJobManager()
    return _MANAGER


@dataclass
class SwitchJob:
    job_id: str
    user_id: str
    target_username: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    stage: str = "queued"  # queued / stopping_queues / checking_token / starting_browser / clicking / done / failed
    message: str = "任务已入队"
    progress: int = 0  # 0..100
    ok: Optional[bool] = None  # None 表示进行中
    listeners: List[asyncio.Queue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "stage": self.stage,
            "message": self.message,
            "progress": self.progress,
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def push_event(self) -> None:
        """向所有监听者推送当前快照。"""
        snapshot = self.to_dict()
        for q in self.listeners:
            try:
                q.put_nowait(snapshot)
            except Exception:
                pass


class SwitchJobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, SwitchJob] = {}
        self._lock = threading.Lock()

    def create_job(self, user_id: str, target_username: str = "") -> SwitchJob:
        job_id = uuid.uuid4().hex[:12]
        job = SwitchJob(job_id=job_id, user_id=user_id, target_username=target_username)
        with self._lock:
            self._jobs[job_id] = job
        # 旧的已完成 job 限制内存：保留最近 16 个
        with self._lock:
            if len(self._jobs) > 32:
                # 移除最旧且已完成的
                finished = sorted(
                    (j for j in self._jobs.values() if j.finished_at is not None),
                    key=lambda j: j.finished_at or 0,
                )
                for old in finished[: len(self._jobs) - 32]:
                    self._jobs.pop(old.job_id, None)
        return job

    def get_job(self, job_id: str) -> Optional[SwitchJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> List[SwitchJob]:
        with self._lock:
            return list(self._jobs.values())

    def update(self, job_id: str, **kwargs: Any) -> None:
        """原子更新 job 字段并向所有 SSE 监听者广播。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.push_event()

    def finish(self, job_id: str, ok: bool, message: str) -> None:
        self.update(
            job_id,
            finished_at=time.time(),
            ok=ok,
            stage="done" if ok else "failed",
            progress=100,
            message=message,
        )

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        """注册 SSE 监听者，返回其专属队列。先收到一份快照。"""
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        # 监听者需要锁保护 list
        with self._lock:
            job.listeners.append(q)
            snap = job.to_dict()
        # 先把当前状态推给订阅者
        await q.put(snap)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            try:
                job.listeners.remove(q)
            except ValueError:
                pass
