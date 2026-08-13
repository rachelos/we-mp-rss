"""
文章导出后台任务管理。

与 core/switch_job.py 同形，独立是为了语义清晰（导出任务的字段
与切换账号不同：total_records / processed_records / skipped_records /
output_path 等）。
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 全局单例
_MANAGER: Optional["ExportJobManager"] = None
_LOCK = threading.Lock()


def get_export_job_manager() -> "ExportJobManager":
    """进程内唯一 ExportJobManager 实例。"""
    global _MANAGER
    if _MANAGER is None:
        with _LOCK:
            if _MANAGER is None:
                _MANAGER = ExportJobManager()
    return _MANAGER


@dataclass
class ExportJob:
    job_id: str
    user_id: str
    mp_id: str
    fmt_summary: str  # e.g. "pdf+md+json"
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    stage: str = "queued"  # queued / counting / rendering_pdfs / converting_docx / writing_files / packaging / done / failed
    message: str = "任务已入队"
    progress: int = 0  # 0..100
    ok: Optional[bool] = None
    total_records: int = 0
    processed_records: int = 0
    skipped_records: int = 0
    output_path: Optional[str] = None
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
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "skipped_records": self.skipped_records,
            "output_path": self.output_path,
            "mp_id": self.mp_id,
            "fmt_summary": self.fmt_summary,
        }

    def push_event(self) -> None:
        snapshot = self.to_dict()
        for q in self.listeners:
            try:
                q.put_nowait(snapshot)
            except asyncio.QueueFull:
                # 订阅者消费太慢；记录一次以便排查，但不要阻塞生产者
                import logging
                logging.getLogger(__name__).warning(
                    "ExportJob SSE listener queue full; dropping snapshot for job_id=%s", self.job_id
                )


class ExportJobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, ExportJob] = {}
        self._lock = threading.Lock()

    def create_job(self, user_id: str, mp_id: str, fmt_summary: str) -> ExportJob:
        job_id = uuid.uuid4().hex[:12]
        job = ExportJob(job_id=job_id, user_id=user_id, mp_id=mp_id, fmt_summary=fmt_summary)
        with self._lock:
            self._jobs[job_id] = job
            # 限制保留数量
            if len(self._jobs) > 32:
                finished = sorted(
                    (j for j in self._jobs.values() if j.finished_at is not None),
                    key=lambda j: j.finished_at or 0,
                )
                for old in finished[: len(self._jobs) - 32]:
                    self._jobs.pop(old.job_id, None)
        return job

    def get_job(self, job_id: str) -> Optional[ExportJob]:
        with self._lock:
            return self._jobs.get(job_id)

    # 仅允许通过 update() 更新的字段；其他内部字段（如 listeners）不可外部写入
    _UPDATABLE = frozenset({
        "stage", "message", "progress", "ok", "finished_at",
        "total_records", "processed_records", "skipped_records", "output_path",
    })

    def update(self, job_id: str, **kwargs: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in kwargs.items():
                if key in self._UPDATABLE:
                    setattr(job, key, value)
            job.push_event()

    def finish(self, job_id: str, ok: bool, message: str, output_path: Optional[str] = None) -> None:
        kw: Dict[str, Any] = dict(
            finished_at=time.time(),
            ok=ok,
            stage="done" if ok else "failed",
            progress=100,
            message=message,
        )
        if output_path is not None:
            kw["output_path"] = output_path
        self.update(job_id, **kw)

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        with self._lock:
            job.listeners.append(q)
            snap = job.to_dict()
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