import time
import threading
import signal
from typing import Dict, List, Callable
from mcp_sandbox.utils.config import logger

class PeriodicTaskManager:
    """Manager for periodic background tasks"""
    
    # 类变量，用于跟踪所有任务线程
    _tasks: Dict[str, Dict] = {}
    _stop_events: Dict[str, threading.Event] = {}
    _lock = threading.Lock()
    
    @classmethod
    def start_task(cls, task_func, interval_seconds: int, task_name: str) -> None:
        """Start a background periodic task"""
        # 如果任务已存在，先停止它
        if task_name in cls._tasks:
            cls.stop_task(task_name)
        
        # 创建停止事件
        stop_event = threading.Event()
        cls._stop_events[task_name] = stop_event
        
        def periodic_runner():
            while not stop_event.is_set():
                try:
                    task_func()
                    # 使用带超时的等待，以便能够响应停止事件
                    stop_event.wait(timeout=interval_seconds)
                except Exception as e:
                    logger.error(f"{task_name} task error: {e}")
                    # 出错时短暂暂停，避免错误循环消耗资源
                    if not stop_event.is_set():
                        stop_event.wait(timeout=1)
        
        # 创建并启动线程
        task_thread = threading.Thread(target=periodic_runner, daemon=True, name=f"task-{task_name}")
        task_thread.start()
        
        # 记录任务信息
        with cls._lock:
            cls._tasks[task_name] = {
                "thread": task_thread,
                "interval": interval_seconds,
                "start_time": time.time()
            }
        
        logger.info(f"Started {task_name} task")
    
    @classmethod
    def stop_task(cls, task_name: str) -> bool:
        """停止指定的任务
        
        Args:
            task_name: 任务名称
            
        Returns:
            是否成功停止任务
        """
        with cls._lock:
            if task_name in cls._stop_events:
                # 设置停止事件
                cls._stop_events[task_name].set()
                
                # 等待线程结束（最多等待3秒）
                if task_name in cls._tasks:
                    thread = cls._tasks[task_name]["thread"]
                    if thread.is_alive():
                        thread.join(timeout=3)
                    
                    # 清理任务记录
                    del cls._tasks[task_name]
                
                # 清理停止事件
                del cls._stop_events[task_name]
                logger.info(f"Stopped {task_name} task")
                return True
        return False
    
    @classmethod
    def stop_all_tasks(cls) -> None:
        """停止所有任务"""
        task_names = list(cls._tasks.keys())
        for task_name in task_names:
            cls.stop_task(task_name)
        logger.info("All periodic tasks stopped")
    
    @classmethod
    def start_file_cleanup(cls, cleanup_func) -> None:
        """Start background task for periodic file cleanup"""
        cls.start_task(cleanup_func, 600, "automatic_file_cleanup")