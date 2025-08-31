"""日志配置模块

提供统一的日志配置、结构化日志记录和性能监控功能。
"""

import logging
import logging.handlers
import json
import time
import functools
import threading
from datetime import datetime
from typing import Dict, Any, Optional, Callable, Union
from pathlib import Path
from contextlib import contextmanager
from enum import Enum


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器
    
    将日志记录格式化为JSON格式，便于日志分析和监控。
    """

    def __init__(self, include_extra: bool = True):
        """初始化格式化器
        
        Args:
            include_extra: 是否包含额外字段
        """
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录
        
        Args:
            record: 日志记录对象
            
        Returns:
            JSON格式的日志字符串
        """
        # 基础日志信息
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": record.thread,
            "thread_name": record.threadName,
            "process_id": record.process
        }

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加额外字段
        if self.include_extra:
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in {
                    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                    'filename', 'module', 'lineno', 'funcName', 'created',
                    'msecs', 'relativeCreated', 'thread', 'threadName',
                    'processName', 'process', 'getMessage', 'exc_info',
                    'exc_text', 'stack_info'
                }:
                    try:
                        # 确保值可以JSON序列化
                        json.dumps(value)
                        extra_fields[key] = value
                    except (TypeError, ValueError):
                        extra_fields[key] = str(value)

            if extra_fields:
                log_data["extra"] = extra_fields

        return json.dumps(log_data, ensure_ascii=False, separators=(',', ':'))


class PerformanceLogger:
    """性能日志记录器
    
    用于记录函数执行时间和性能指标。
    """

    def __init__(self, logger_name: str = "performance"):
        """初始化性能日志记录器
        
        Args:
            logger_name: 日志记录器名称
        """
        self.logger = logging.getLogger(logger_name)
        self._metrics: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    @contextmanager
    def measure(self, operation: str, **context):
        """测量操作执行时间
        
        Args:
            operation: 操作名称
            **context: 上下文信息
        """
        start_time = time.time()
        start_memory = self._get_memory_usage()

        try:
            yield
            success = True
            error = None
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            end_time = time.time()
            end_memory = self._get_memory_usage()

            duration = end_time - start_time
            memory_delta = end_memory - start_memory if end_memory and start_memory else None

            # 记录性能指标
            self._record_metric(operation, duration, memory_delta, success, error, context)

    def _get_memory_usage(self) -> Optional[float]:
        """获取当前内存使用量（MB）
        
        Returns:
            内存使用量，如果无法获取则返回None
        """
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # 转换为MB
        except ImportError:
            return None
        except Exception:
            return None

    def _record_metric(
            self,
            operation: str,
            duration: float,
            memory_delta: Optional[float],
            success: bool,
            error: Optional[str],
            context: Dict[str, Any]
    ) -> None:
        """记录性能指标
        
        Args:
            operation: 操作名称
            duration: 执行时间
            memory_delta: 内存变化量
            success: 是否成功
            error: 错误信息
            context: 上下文信息
        """
        with self._lock:
            # 更新统计信息
            if operation not in self._metrics:
                self._metrics[operation] = {
                    "count": 0,
                    "total_duration": 0.0,
                    "min_duration": float('inf'),
                    "max_duration": 0.0,
                    "success_count": 0,
                    "error_count": 0
                }

            metrics = self._metrics[operation]
            metrics["count"] += 1
            metrics["total_duration"] += duration
            metrics["min_duration"] = min(metrics["min_duration"], duration)
            metrics["max_duration"] = max(metrics["max_duration"], duration)

            if success:
                metrics["success_count"] += 1
            else:
                metrics["error_count"] += 1

        # 记录详细日志
        log_data = {
            "operation": operation,
            "duration_ms": round(duration * 1000, 2),
            "success": success,
            "timestamp": datetime.now().isoformat()
        }

        if memory_delta is not None:
            log_data["memory_delta_mb"] = round(memory_delta, 2)

        if error:
            log_data["error"] = error

        if context:
            log_data["context"] = context

        # 根据执行时间和成功状态选择日志级别
        if not success:
            self.logger.error("操作执行失败", extra=log_data)
        elif duration > 5.0:  # 超过5秒的操作记录为警告
            self.logger.warning("操作执行缓慢", extra=log_data)
        elif duration > 1.0:  # 超过1秒的操作记录为信息
            self.logger.info("操作执行完成", extra=log_data)
        else:
            self.logger.debug("操作执行完成", extra=log_data)

    def get_metrics(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """获取性能指标
        
        Args:
            operation: 操作名称，如果为None则返回所有指标
            
        Returns:
            性能指标字典
        """
        with self._lock:
            if operation:
                if operation in self._metrics:
                    metrics = self._metrics[operation].copy()
                    if metrics["count"] > 0:
                        metrics["avg_duration"] = metrics["total_duration"] / metrics["count"]
                        metrics["success_rate"] = metrics["success_count"] / metrics["count"]
                    return metrics
                else:
                    return {}
            else:
                result = {}
                for op, metrics in self._metrics.items():
                    op_metrics = metrics.copy()
                    if op_metrics["count"] > 0:
                        op_metrics["avg_duration"] = op_metrics["total_duration"] / op_metrics["count"]
                        op_metrics["success_rate"] = op_metrics["success_count"] / op_metrics["count"]
                    result[op] = op_metrics
                return result

    def reset_metrics(self, operation: Optional[str] = None) -> None:
        """重置性能指标
        
        Args:
            operation: 操作名称，如果为None则重置所有指标
        """
        with self._lock:
            if operation:
                if operation in self._metrics:
                    del self._metrics[operation]
            else:
                self._metrics.clear()


class LoggingConfig:
    """日志配置管理器
    
    提供统一的日志配置和管理功能。
    """

    def __init__(self):
        """初始化日志配置管理器"""
        self._configured = False
        self._performance_logger = PerformanceLogger()

    def setup_logging(
            self,
            level: Union[str, int, LogLevel] = LogLevel.INFO,
            log_file: Optional[str] = None,
            max_file_size: int = 10 * 1024 * 1024,  # 10MB
            backup_count: int = 5,
            use_structured_format: bool = False,
            console_output: bool = True,
            logger_name: Optional[str] = None
    ) -> logging.Logger:
        """设置日志配置
        
        Args:
            level: 日志级别
            log_file: 日志文件路径
            max_file_size: 日志文件最大大小（字节）
            backup_count: 备份文件数量
            use_structured_format: 是否使用结构化格式
            console_output: 是否输出到控制台
            logger_name: 日志记录器名称
            
        Returns:
            配置好的日志记录器
        """
        # 转换日志级别
        if isinstance(level, LogLevel):
            log_level = level.value
        elif isinstance(level, str):
            log_level = getattr(logging, level.upper(), logging.INFO)
        else:
            log_level = level

        # 获取根日志记录器或指定名称的记录器
        logger = logging.getLogger(logger_name)

        # 避免重复配置
        if self._configured and not logger_name:
            return logger

        # 清除现有处理器
        logger.handlers.clear()
        logger.setLevel(log_level)

        # 选择格式化器
        if use_structured_format:
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )

        # 控制台处理器
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # 文件处理器
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_file_size,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        # 防止日志传播到父记录器（避免重复输出）
        if logger_name:
            logger.propagate = False

        if not logger_name:
            self._configured = True

        return logger

    def get_performance_logger(self) -> PerformanceLogger:
        """获取性能日志记录器
        
        Returns:
            性能日志记录器实例
        """
        return self._performance_logger

    def create_audit_logger(self, name: str = "audit") -> logging.Logger:
        """创建审计日志记录器
        
        Args:
            name: 审计日志记录器名称
            
        Returns:
            审计日志记录器
        """
        audit_logger = logging.getLogger(name)

        # 如果已经配置过，直接返回
        if audit_logger.handlers:
            return audit_logger

        # 设置审计日志格式
        formatter = StructuredFormatter()

        # 审计日志文件处理器
        audit_file = Path("logs") / "audit.log"
        audit_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            audit_file,
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        audit_logger.addHandler(file_handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False

        return audit_logger


# 全局日志配置实例
logging_config = LoggingConfig()


def performance_monitor(operation_name: Optional[str] = None, **context):
    """性能监控装饰器
    
    Args:
        operation_name: 操作名称，默认使用函数名
        **context: 上下文信息
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            perf_logger = logging_config.get_performance_logger()

            with perf_logger.measure(op_name, **context):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def get_logger(name: str, **config_kwargs) -> logging.Logger:
    """获取配置好的日志记录器
    
    Args:
        name: 日志记录器名称
        **config_kwargs: 日志配置参数
        
    Returns:
        配置好的日志记录器
    """
    return logging_config.setup_logging(logger_name=name, **config_kwargs)


def log_function_call(include_args: bool = False, include_result: bool = False):
    """函数调用日志装饰器
    
    Args:
        include_args: 是否包含参数信息
        include_result: 是否包含返回结果
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)

            # 构建日志信息
            log_data = {
                "function": func.__name__,
                "module": func.__module__
            }

            if include_args:
                log_data["args"] = str(args)[:200]  # 限制长度
                log_data["kwargs"] = str(kwargs)[:200]

            logger.debug("函数调用开始", extra=log_data)

            try:
                result = func(*args, **kwargs)

                if include_result:
                    log_data["result"] = str(result)[:200]

                logger.debug("函数调用成功", extra=log_data)
                return result

            except Exception as e:
                log_data["error"] = str(e)
                logger.error("函数调用失败", extra=log_data, exc_info=True)
                raise

        return wrapper

    return decorator
