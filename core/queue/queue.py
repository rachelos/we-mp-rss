import queue
import threading
import time
import gc
import json
from typing import Callable, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from core.print import print_error, print_info, print_warning, print_success

# Redis 键前缀 - 主队列（文章列表采集）
REDIS_KEY_PREFIX = "werss:queue"
REDIS_KEY_PENDING = f"{REDIS_KEY_PREFIX}:pending"
REDIS_KEY_CURRENT = f"{REDIS_KEY_PREFIX}:current"
REDIS_KEY_HISTORY = f"{REDIS_KEY_PREFIX}:history"
REDIS_KEY_STATUS = f"{REDIS_KEY_PREFIX}:status"

# Redis 键前缀 - 内容补抓队列
CONTENT_REDIS_KEY_PREFIX = "werss:content_queue"
CONTENT_REDIS_KEY_PENDING = f"{CONTENT_REDIS_KEY_PREFIX}:pending"
CONTENT_REDIS_KEY_CURRENT = f"{CONTENT_REDIS_KEY_PREFIX}:current"
CONTENT_REDIS_KEY_HISTORY = f"{CONTENT_REDIS_KEY_PREFIX}:history"
CONTENT_REDIS_KEY_STATUS = f"{CONTENT_REDIS_KEY_PREFIX}:status"

# 全局 Redis 客户端（延迟初始化）
_redis_client = None

# 全局队列实例引用（用于广播）
_task_queue_instance = None
_content_queue_instance = None


def _broadcast_queue_status():
    """广播所有队列状态到 WebSocket 连接"""
    try:
        from core.ws_manager import ws_manager
        status = get_all_queues_status()
        ws_manager.broadcast_sync({
            "type": "queue_status",
            "data": status
        })
    except Exception as e:
        print_error(f"广播队列状态失败: {e}")


def get_all_queues_status() -> dict:
    """获取所有队列的状态"""
    global _task_queue_instance, _content_queue_instance
    return {
        'main_queue': _task_queue_instance.get_detailed_status() if _task_queue_instance else None,
        'content_queue': _content_queue_instance.get_detailed_status() if _content_queue_instance else None
    }


def _get_redis():
    """获取 Redis 客户端（延迟初始化）"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    try:
        import redis
        from core.config import cfg
        
        redis_url = cfg.get("redis.url", "")
        if not redis_url:
            print_info("Redis URL 未配置，队列状态将仅在进程内共享")
            return None
        
        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True
        )
        # 测试连接
        _redis_client.ping()
        print_info("Queue Redis 连接成功")
        return _redis_client
    except Exception as e:
        print_error(f"Queue Redis 连接失败: {e}")
        _redis_client = None
        return None


@dataclass
class TaskItem:
    """待执行任务项"""
    task_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    max_retries: int = 3
    
    def _serialize_value(self, value: Any) -> Any:
        """安全序列化值，处理不可 JSON 序列化的对象"""
        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        else:
            # 对于复杂对象，返回其字符串表示
            return repr(value)
    
    def to_dict(self) -> dict:
        return {
            'task_name': self.task_name,
            'args': self._serialize_value(list(self.args) if self.args else []),
            'kwargs': self._serialize_value(self.kwargs),
            'max_retries': self.max_retries
        }


@dataclass
class TaskRecord:
    """任务执行记录"""
    task_name: str
    start_time: str
    end_time: Optional[str] = None
    duration: Optional[float] = None
    status: str = "running"  # running, completed, failed
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'task_name': self.task_name,
            'start_time': self.start_time,
            'end_time': self.end_time or '',
            'duration': self.duration or 0,
            'status': self.status,
            'error': self.error or ''
        }


class TaskQueueManager:
    """任务队列管理器，用于管理和执行排队任务（支持多进程）"""
    
    def __init__(self, maxsize=0, tag="", redis_prefix=None):
        """初始化任务队列
        
        Args:
            maxsize: 队列最大大小
            tag: 队列标签
            redis_prefix: Redis 键前缀配置，包含 pending, current, history, status
        """
        self._queue = queue.Queue(maxsize=maxsize)
        self._thread_lock = threading.Lock()
        self._is_running = False
        self.tag = tag
        # 任务历史记录（最近100条）
        self._history: list[TaskRecord] = []
        self._history_max_size = 100
        # 当前执行的任务
        self._current_task: Optional[TaskRecord] = None
        # 待执行任务列表（用于展示）
        self._pending_items: list[TaskItem] = []
        self._instance_id = id(self)
        
        # Redis 键前缀配置
        self._redis_keys = redis_prefix or {
            'pending': REDIS_KEY_PENDING,
            'current': REDIS_KEY_CURRENT,
            'history': REDIS_KEY_HISTORY,
            'status': REDIS_KEY_STATUS
        }
        
        print_info(f"TaskQueueManager initialized, instance id: {self._instance_id}, tag: {tag}")
        
    def _save_pending_to_redis(self):
        """保存待执行任务到 Redis"""
        redis_client = _get_redis()
        if not redis_client:
            return
        
        try:
            pending_list = [item.to_dict() for item in self._pending_items]
            redis_client.delete(self._redis_keys['pending'])
            if pending_list:
                for item in pending_list:
                    redis_client.rpush(self._redis_keys['pending'], json.dumps(item, ensure_ascii=False))
        except Exception as e:
            print_error(f"保存待执行任务到 Redis 失败: {e}")
    
    def _save_current_task_to_redis(self, task_record: Optional[TaskRecord]):
        """保存当前任务到 Redis"""
        redis_client = _get_redis()
        if not redis_client:
            return
        
        try:
            if task_record:
                redis_client.hset(self._redis_keys['current'], mapping=task_record.to_dict())
            else:
                redis_client.delete(self._redis_keys['current'])
        except Exception as e:
            print_error(f"保存当前任务到 Redis 失败: {e}")
    
    def _save_history_to_redis(self, task_record: TaskRecord):
        """保存历史记录到 Redis"""
        redis_client = _get_redis()
        if not redis_client:
            return
        
        try:
            redis_client.lpush(self._redis_keys['history'], json.dumps(task_record.to_dict(), ensure_ascii=False))
            redis_client.ltrim(self._redis_keys['history'], 0, self._history_max_size - 1)
        except Exception as e:
            print_error(f"保存历史记录到 Redis 失败: {e}")
    
    def _clear_history_from_redis(self):
        """清空 Redis 历史记录"""
        redis_client = _get_redis()
        if not redis_client:
            return
        
        try:
            redis_client.delete(self._redis_keys['history'])
        except Exception as e:
            print_error(f"清空 Redis 历史记录失败: {e}")
    
    def _save_status_to_redis(self):
        """保存队列状态到 Redis"""
        redis_client = _get_redis()
        if not redis_client:
            return
        
        try:
            redis_client.hset(self._redis_keys['status'], mapping={
                'is_running': str(self._is_running).lower(),
                'tag': self.tag or '',
                'pending_count': self._queue.qsize(),
                'history_count': len(self._history)
            })
        except Exception as e:
            print_error(f"保存队列状态到 Redis 失败: {e}")
    
    def _get_pending_from_redis(self) -> list:
        """从 Redis 获取待执行任务"""
        redis_client = _get_redis()
        if not redis_client:
            return []
        
        try:
            items = redis_client.lrange(self._redis_keys['pending'], 0, -1)
            return [json.loads(item) for item in items]
        except Exception as e:
            print_error(f"从 Redis 获取待执行任务失败: {e}")
            return []
    
    def _get_current_task_from_redis(self) -> Optional[dict]:
        """从 Redis 获取当前任务"""
        redis_client = _get_redis()
        if not redis_client:
            return None
        
        try:
            data = redis_client.hgetall(self._redis_keys['current'])
            if data and 'task_name' in data:
                return data
            return None
        except Exception as e:
            print_error(f"从 Redis 获取当前任务失败: {e}")
            return None
    
    def _get_history_from_redis(self, limit: int = 20) -> list:
        """从 Redis 获取历史记录（兼容旧接口）"""
        redis_client = _get_redis()
        if not redis_client:
            return []
        
        try:
            items = redis_client.lrange(self._redis_keys['history'], 0, limit - 1)
            return [json.loads(item) for item in items]
        except Exception as e:
            print_error(f"从 Redis 获取历史记录失败: {e}")
            return []
    
    def _get_history_page_from_redis(self, page: int = 1, page_size: int = 10) -> dict:
        """从 Redis 获取分页历史记录
        
        Args:
            page: 页码，从1开始
            page_size: 每页数量
            
        Returns:
            dict: 包含 history, total, page, page_size, total_pages
        """
        redis_client = _get_redis()
        if not redis_client:
            return {'history': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0}
        
        try:
            total = redis_client.llen(self._redis_keys['history'])
            total_pages = (total + page_size - 1) // page_size if total > 0 else 0
            
            # Redis 列表是从新到旧存储的（LPUSH），所以计算偏移量
            start = (page - 1) * page_size
            end = start + page_size - 1
            
            items = redis_client.lrange(self._redis_keys['history'], start, end)
            history = [json.loads(item) for item in items]
            
            return {
                'history': history,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages
            }
        except Exception as e:
            print_error(f"从 Redis 获取分页历史记录失败: {e}")
            return {'history': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0}
    
    def _get_history_count_from_redis(self) -> int:
        """从 Redis 获取历史记录数量"""
        redis_client = _get_redis()
        if not redis_client:
            return 0
        
        try:
            return redis_client.llen(self._redis_keys['history'])
        except Exception as e:
            print_error(f"从 Redis 获取历史记录数量失败: {e}")
            return 0
        
    def add_task(self, task: Callable[..., Any], *args: Any, max_retries: int = 3, task_name: str = None, **kwargs: Any) -> bool:
        """添加任务到队列
        
        Args:
            task: 要执行的任务函数
            *args: 任务函数的参数
            max_retries: 最大重试次数，默认3次
            task_name: 自定义任务名称（可选），用于显示，如公众号名称
            **kwargs: 任务函数的关键字参数
            
        Returns:
            bool: 是否成功添加到队列
        """
        broadcast_needed = False
        
        with self._thread_lock:
            # 获取任务显示名称
            display_name = task_name or getattr(task, '__name__', str(task))
            
            # 检查任务是否已在队列中（根据 task_name 去重）
            for pending_item in self._pending_items:
                if pending_item.task_name == display_name:
                    print_warning(f"{self.tag}任务已在队列中，跳过 [{display_name}]")
                    return False
            
            # 检查队列是否已满（如果设置了maxsize）
            try:
                # 将 task_name 存储在队列项中
                self._queue.put_nowait((task, args, kwargs, max_retries, task_name))
            except queue.Full:
                print_error(f"{self.tag}队列已满，任务添加失败")
                return False
                
            # 记录待执行任务
            self._pending_items.append(TaskItem(
                task_name=display_name,
                args=args,
                kwargs=kwargs,
                max_retries=max_retries
            ))
            
            # 优化：只追加新任务到 Redis，而不是全量重写
            redis_client = _get_redis()
            if redis_client:
                try:
                    new_item = self._pending_items[-1].to_dict()
                    redis_client.rpush(self._redis_keys['pending'], json.dumps(new_item, ensure_ascii=False))
                    # 只更新计数，不保存完整状态
                    redis_client.hincrby(self._redis_keys['status'], 'pending_count', 1)
                except Exception as e:
                    print_error(f"追加任务到 Redis 失败: {e}")
            
            # 标记需要广播，但不在这里执行（避免在锁内进行异步操作）
            broadcast_needed = True
            
        # 在锁外执行广播，避免阻塞 FastAPI 的事件循环
        if broadcast_needed:
            _broadcast_queue_status()
            
        # print_success(f"{self.tag}队列任务添加成功 [{display_name}]\n")
        return True
        
    def run_task_background(self)->None:
        threading.Thread(target=self.run_tasks, daemon=True).start()  
        print_warning(f"队列任务后台运行, instance id: {self._instance_id}")
        
    def run_tasks(self, timeout: float = 1.0) -> None:
        """执行队列中的所有任务，并持续运行以接收新任务
        
        Args:
            timeout: 等待新任务的超时时间(秒)
        """
        with self._thread_lock:
            if self._is_running:
                return
            self._is_running = True
            self._save_status_to_redis()
            
        try:
            while self._is_running:
                time.sleep(0.1)  # 避免过于频繁的任务获取 
                try:
                    # 阻塞获取任务，避免CPU空转
                    task_item = self._queue.get(timeout=timeout)
                    
                    # 兼容多种格式：5个元素(新格式带task_name)，4个元素，3个元素(旧格式)
                    if len(task_item) == 5:
                        task, args, kwargs, max_retries, custom_task_name = task_item
                    elif len(task_item) == 4:
                        task, args, kwargs, max_retries = task_item
                        custom_task_name = None
                    else:
                        task, args, kwargs = task_item
                        max_retries = 3
                        custom_task_name = None
                    
                    # 从待执行列表中移除
                    with self._thread_lock:
                        if self._pending_items:
                            self._pending_items.pop(0)
                            self._save_pending_to_redis()
                    
                    # 记录任务开始 - 优先使用自定义名称
                    task_name = custom_task_name or getattr(task, '__name__', str(task))
                    with self._thread_lock:
                        self._current_task = TaskRecord(
                            task_name=task_name,
                            start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        # 保存当前任务到 Redis
                        self._save_current_task_to_redis(self._current_task)
                    
                    # 广播队列状态更新（任务开始）
                    _broadcast_queue_status()
                    
                    print_info(f"Task started: {task_name}")
                    
                    retry_count = 0
                    success = False
                    last_error = None
                    start_time = time.time()  # 提前定义，确保异常时可用
                    
                    while retry_count <= max_retries and not success:
                        if retry_count > 0:
                            print_warning(f"任务 [{task_name}] 第 {retry_count} 次重试...")
                            time.sleep(2 ** retry_count)  # 指数退避
                            
                        try:
                            # 记录任务开始时间
                            start_time = time.time()
                            task_executor = ThreadPoolExecutor(max_workers=1)
                            try:
                                future = task_executor.submit(task, *args, **kwargs)
                                future.result(timeout=600)
                            except FutureTimeoutError:
                                print_error("Task [{}] execution timeout (10 min)".format(task_name))
                                raise Exception("Task timed out after 600s")
                            finally:
                                task_executor.shutdown(wait=False)
                            # 记录任务执行时间
                            duration = time.time() - start_time
                            
                            # 更新当前任务记录
                            with self._thread_lock:
                                if self._current_task:
                                    self._current_task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    self._current_task.duration = duration
                                    self._current_task.status = "completed"
                            
                            print_info(f"\n任务执行完成，耗时: {duration:.2f}秒")
                            success = True
                            
                        except Exception as e:
                            last_error = e
                            retry_count += 1
                            
                            if retry_count <= max_retries:
                                print_warning(f"任务 [{task_name}] 执行失败: {e}，准备重试 ({retry_count}/{max_retries})")
                            else:
                                # 达到最大重试次数，记录失败
                                with self._thread_lock:
                                    if self._current_task:
                                        self._current_task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        self._current_task.duration = time.time() - start_time
                                        self._current_task.status = "failed"
                                        self._current_task.error = str(e)
                                
                                print_error(f"任务 [{task_name}] 执行失败，已达到最大重试次数: {e}")
                    
                    # 保存到历史记录
                    with self._thread_lock:
                        if self._current_task:
                            self._history.append(self._current_task)
                            # 保存到 Redis
                            self._save_history_to_redis(self._current_task)
                            print_info(f"Task completed and saved to history. Local count: {len(self._history)}")
                            # 限制历史记录大小
                            if len(self._history) > self._history_max_size:
                                self._history = self._history[-self._history_max_size:]
                            self._current_task = None
                            # 清除 Redis 当前任务
                            self._save_current_task_to_redis(None)
                            self._save_status_to_redis()
                    
                    # 广播队列状态更新（任务完成）
                    _broadcast_queue_status()
                    
                    # 确保任务完成标记和资源释放
                    self._queue.task_done()
                    # 强制垃圾回收
                    gc.collect()
                    
                except queue.Empty:
                    # 超时无任务，继续检查运行状态
                    continue
                    
        finally:
            # 确保停止状态设置和资源清理
            with self._thread_lock:
                self._is_running = False
                self._save_status_to_redis()
            # 清理可能残留的资源
            gc.collect()
    
    def stop(self) -> None:
        """停止任务执行"""
        with self._thread_lock:
            self._is_running = False
            self._save_status_to_redis()
    
    def get_queue_info(self) -> dict:
        """
        获取队列的当前状态信息
        
        返回:
            dict: 包含队列信息的字典，包括:
                - is_running: 队列是否正在运行
                - pending_tasks: 等待执行的任务数量
        """
        with self._thread_lock:
            return {
                'is_running': self._is_running,
                'pending_tasks': self._queue.qsize()
            }
    
    def get_detailed_status(self) -> dict:
        """
        获取队列的详细状态信息（从 Redis 读取，支持多进程）
        
        返回:
            dict: 包含详细队列信息的字典
        """
        # 从 Redis 获取数据
        pending_list = self._get_pending_from_redis()
        history_list = self._get_history_from_redis(20)
        history_count = self._get_history_count_from_redis()
        current_task = self._get_current_task_from_redis()
        
        # 获取运行状态
        redis_client = _get_redis()
        is_running = self._is_running
        if redis_client:
            try:
                status = redis_client.hgetall(self._redis_keys['status'])
                if status and 'is_running' in status:
                    is_running = status['is_running'] == 'true'
            except Exception:
                pass
        
        return {
            'tag': self.tag,
            'is_running': is_running,
            'pending_count': len(pending_list),
            'pending_tasks': pending_list,
            'current_task': current_task,
            'history_count': history_count,
            'recent_history': history_list
        }
    
    def clear_history(self) -> None:
        """清空任务历史记录"""
        broadcast_needed = False
        with self._thread_lock:
            self._history.clear()
            self._clear_history_from_redis()
            self._save_status_to_redis()
            # 标记需要广播，但不在这里执行
            broadcast_needed = True
        
        # 在锁外执行广播
        if broadcast_needed:
            _broadcast_queue_status()
        print_success("任务历史记录已清空")
            
    def clear_queue(self) -> None:
        """清空队列中的所有任务"""
        broadcast_needed = False
        with self._thread_lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
            self._pending_items.clear()
            self._save_pending_to_redis()
            self._save_status_to_redis()
            # 标记需要广播，但不在这里执行
            broadcast_needed = True
        
        # 在锁外执行广播
        if broadcast_needed:
            _broadcast_queue_status()
        print_success("队列已清空")
            
    def delete_queue(self) -> None:
        """删除队列(停止并清空所有任务)"""
        with self._thread_lock:
            self._is_running = False
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
            self._save_status_to_redis()
            print_success("队列已删除")

# 创建全局单例（模块级变量，确保唯一实例）
TaskQueue = TaskQueueManager(tag="文章采集")
_task_queue_instance = TaskQueue  # 设置全局实例引用
print_info(f"TaskQueue singleton created, instance id: {TaskQueue._instance_id}")
TaskQueue.run_task_background()

# 内容补抓队列
ContentTaskQueue = TaskQueueManager(
    tag="内容补抓",
    redis_prefix={
        'pending': CONTENT_REDIS_KEY_PENDING,
        'current': CONTENT_REDIS_KEY_CURRENT,
        'history': CONTENT_REDIS_KEY_HISTORY,
        'status': CONTENT_REDIS_KEY_STATUS
    }
)
_content_queue_instance = ContentTaskQueue  # 设置全局实例引用
print_info(f"ContentTaskQueue singleton created, instance id: {ContentTaskQueue._instance_id}")
ContentTaskQueue.run_task_background()

if __name__ == "__main__":
    def task1():
        print("执行任务1")

    def task2(name):
        print(f"执行任务2，参数: {name}")

    manager = TaskQueueManager()
    manager.add_task(task1)
    manager.add_task(task2, "测试任务")
    manager.run_tasks()  # 按顺序执行任务1和任务2
