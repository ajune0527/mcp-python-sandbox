"""异常处理模块

定义项目中使用的自定义异常类型，提供统一的异常处理机制。
"""

import logging
import traceback
from typing import Optional, Dict, Any, Union, Type, Callable
from functools import wraps
from enum import Enum
from datetime import datetime

try:
    from .logging_config import get_logger, performance_monitor
except ImportError:
    # 如果日志配置模块不可用，使用标准日志
    def get_logger(name: str, **kwargs):
        return logging.getLogger(name)


    def performance_monitor(operation_name: str = None, **kwargs):
        def decorator(func):
            return func

        return decorator


class ErrorCode(Enum):
    """错误代码枚举"""

    # 通用错误 (1000-1999)
    UNKNOWN_ERROR = 1000
    INVALID_PARAMETER = 1001
    RESOURCE_NOT_FOUND = 1002
    PERMISSION_DENIED = 1003
    OPERATION_TIMEOUT = 1004
    RATE_LIMIT_EXCEEDED = 1005

    # 认证错误 (2000-2999)
    AUTHENTICATION_FAILED = 2000
    INVALID_TOKEN = 2001
    TOKEN_EXPIRED = 2002
    INVALID_API_KEY = 2003
    USER_NOT_FOUND = 2004
    INVALID_CREDENTIALS = 2005

    # 沙盒错误 (3000-3999)
    SANDBOX_CREATION_FAILED = 3000
    SANDBOX_NOT_FOUND = 3001
    SANDBOX_LIMIT_EXCEEDED = 3002
    CONTAINER_START_FAILED = 3003
    CONTAINER_STOP_FAILED = 3004
    CONTAINER_REMOVE_FAILED = 3005
    CODE_EXECUTION_FAILED = 3006
    CODE_EXECUTION_TIMEOUT = 3007

    # Docker错误 (4000-4999)
    DOCKER_CONNECTION_FAILED = 4000
    DOCKER_IMAGE_NOT_FOUND = 4001
    DOCKER_BUILD_FAILED = 4002
    DOCKER_API_ERROR = 4003
    DOCKER_PERMISSION_DENIED = 4004

    # 数据库错误 (5000-5999)
    DATABASE_CONNECTION_FAILED = 5000
    DATABASE_QUERY_FAILED = 5001
    DATABASE_TRANSACTION_FAILED = 5002
    DATABASE_CONSTRAINT_VIOLATION = 5003
    DATABASE_TIMEOUT = 5004

    # 文件系统错误 (6000-6999)
    FILE_NOT_FOUND = 6000
    FILE_PERMISSION_DENIED = 6001
    FILE_SIZE_EXCEEDED = 6002
    INVALID_FILE_FORMAT = 6003
    DISK_SPACE_INSUFFICIENT = 6004

    # 网络错误 (7000-7999)
    NETWORK_CONNECTION_FAILED = 7000
    NETWORK_TIMEOUT = 7001
    INVALID_URL = 7002
    HTTP_ERROR = 7003


class MCPSandboxException(Exception):
    """MCP Sandbox 基础异常类
    
    所有自定义异常的基类，提供统一的异常处理接口。
    """

    def __init__(
            self,
            message: str,
            error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        """初始化异常
        
        Args:
            message: 错误消息
            error_code: 错误代码
            details: 错误详细信息
            cause: 原始异常
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause
        self.timestamp = datetime.now()

        # 记录异常信息
        self._log_exception()

    def _log_exception(self) -> None:
        """记录异常信息到日志"""
        logger = logging.getLogger(self.__class__.__module__)

        # 构建结构化日志信息
        log_extra = {
            "error_code": self.error_code.value,
            "error_name": self.error_code.name,
            "exception_type": self.__class__.__name__,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }

        if self.cause:
            log_extra["original_exception"] = type(self.cause).__name__
            log_extra["original_message"] = str(self.cause)

        # 构建日志消息
        log_message = f"[{self.error_code.name}] {self.message}"

        # 根据错误严重程度选择日志级别
        if self.error_code.value < 2000:
            logger.warning(log_message, extra=log_extra)
        elif self.error_code.value < 5000:
            logger.error(log_message, extra=log_extra, exc_info=True)
        else:
            logger.critical(log_message, extra=log_extra, exc_info=True)

    def to_dict(self) -> Dict[str, Any]:
        """将异常转换为字典格式
        
        Returns:
            包含异常信息的字典
        """
        return {
            "error_code": self.error_code.value,
            "error_name": self.error_code.name,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "traceback": traceback.format_exc() if self.cause else None
        }

    def __str__(self) -> str:
        """字符串表示"""
        return f"[{self.error_code.name}] {self.message}"


class AuthenticationError(MCPSandboxException):
    """认证相关异常"""

    def __init__(
            self,
            message: str = "认证失败",
            error_code: ErrorCode = ErrorCode.AUTHENTICATION_FAILED,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message, error_code, details, cause)


class SandboxError(MCPSandboxException):
    """沙盒相关异常"""

    def __init__(
            self,
            message: str = "沙盒操作失败",
            error_code: ErrorCode = ErrorCode.SANDBOX_CREATION_FAILED,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message, error_code, details, cause)


class DockerError(MCPSandboxException):
    """Docker相关异常"""

    def __init__(
            self,
            message: str = "Docker操作失败",
            error_code: ErrorCode = ErrorCode.DOCKER_CONNECTION_FAILED,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message, error_code, details, cause)


class DatabaseError(MCPSandboxException):
    """数据库相关异常"""

    def __init__(
            self,
            message: str = "数据库操作失败",
            error_code: ErrorCode = ErrorCode.DATABASE_CONNECTION_FAILED,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message, error_code, details, cause)


class FileSystemError(MCPSandboxException):
    """文件系统相关异常"""

    def __init__(
            self,
            message: str = "文件系统操作失败",
            error_code: ErrorCode = ErrorCode.FILE_NOT_FOUND,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message, error_code, details, cause)


class ValidationError(MCPSandboxException):
    """数据验证异常"""

    def __init__(
            self,
            message: str = "数据验证失败",
            error_code: ErrorCode = ErrorCode.INVALID_PARAMETER,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message, error_code, details, cause)


class RateLimitError(MCPSandboxException):
    """速率限制异常"""

    def __init__(
            self,
            message: str = "请求频率超出限制",
            error_code: ErrorCode = ErrorCode.RATE_LIMIT_EXCEEDED,
            details: Optional[Dict[str, Any]] = None,
            cause: Optional[Exception] = None
    ):
        super().__init__(message, error_code, details, cause)


class MCPDatabaseError(DatabaseError):
    """MCP数据库异常（向后兼容别名）"""
    pass


class ExceptionHandler:
    """异常处理器
    
    提供统一的异常处理和转换功能。
    """

    def __init__(self, logger_name: str = "mcp_sandbox.exceptions"):
        """初始化异常处理器
        
        Args:
            logger_name: 日志记录器名称
        """
        try:
            self.logger = get_logger(logger_name, use_structured_format=True)
        except Exception:
            self.logger = logging.getLogger(logger_name)

    def handle_exception(
            self,
            exc: Exception,
            context: Optional[Dict[str, Any]] = None,
            reraise: bool = True
    ) -> Optional['MCPSandboxException']:
        """处理异常
        
        Args:
            exc: 原始异常
            context: 异常上下文信息
            reraise: 是否重新抛出异常
            
        Returns:
            转换后的MCP异常，如果reraise为True则返回None
            
        Raises:
            MCPSandboxException: 转换后的异常（当reraise为True时）
        """
        # 如果已经是MCP异常，直接处理
        if isinstance(exc, MCPSandboxException):
            if context:
                exc.details.update(context)
            if reraise:
                raise exc
            return exc

        # 转换标准异常为MCP异常
        mcp_exc = self._convert_to_mcp_exception(exc, context)

        if reraise:
            raise mcp_exc
        return mcp_exc

    def convert_exception(
            self,
            exc: Exception,
            default_exception_type: Type['MCPSandboxException'] = None
    ) -> 'MCPSandboxException':
        """转换异常为MCP异常
        
        Args:
            exc: 原始异常
            default_exception_type: 默认异常类型
            
        Returns:
            转换后的MCP异常
        """
        if isinstance(exc, MCPSandboxException):
            return exc

        return self._convert_to_mcp_exception(exc)

    def handle_docker_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> 'DockerError':
        """处理Docker相关错误
        
        Args:
            error: 原始异常
            context: 上下文信息
            
        Returns:
            DockerError实例
        """
        error_msg = str(error)

        # 根据错误信息确定具体的错误代码
        if "permission denied" in error_msg.lower():
            code = ErrorCode.DOCKER_PERMISSION_DENIED
        elif "not found" in error_msg.lower():
            code = ErrorCode.DOCKER_IMAGE_NOT_FOUND
        elif "timeout" in error_msg.lower():
            code = ErrorCode.OPERATION_TIMEOUT
        else:
            code = ErrorCode.DOCKER_API_ERROR

        docker_error = DockerError(
            message=f"Docker操作失败: {error_msg}",
            error_code=code,
            details=context or {},
            cause=error
        )

        self.logger.error(
            f"Docker错误: {docker_error.message}",
            extra={
                "error_code": docker_error.error_code.value,
                "original_error": error_msg,
                "context": context or {},
                "exception_type": type(error).__name__,
                "severity": "high" if code in [ErrorCode.DOCKER_PERMISSION_DENIED,
                                               ErrorCode.OPERATION_TIMEOUT] else "medium"
            },
            exc_info=True
        )

        return docker_error

    def _convert_to_mcp_exception(
            self,
            exc: Exception,
            context: Optional[Dict[str, Any]] = None
    ) -> MCPSandboxException:
        """将标准异常转换为MCP异常
        
        Args:
            exc: 原始异常
            context: 异常上下文信息
            
        Returns:
            转换后的MCP异常
        """
        exc_type = type(exc).__name__
        message = str(exc)
        details = context or {}
        details["original_exception"] = exc_type

        # 根据异常类型进行转换
        if "docker" in exc_type.lower() or "container" in exc_type.lower():
            if "not found" in message.lower():
                return DockerError(
                    f"Docker镜像或容器未找到: {message}",
                    ErrorCode.DOCKER_IMAGE_NOT_FOUND,
                    details,
                    exc
                )
            elif "permission" in message.lower():
                return DockerError(
                    f"Docker权限不足: {message}",
                    ErrorCode.DOCKER_PERMISSION_DENIED,
                    details,
                    exc
                )
            else:
                return DockerError(
                    f"Docker操作失败: {message}",
                    ErrorCode.DOCKER_API_ERROR,
                    details,
                    exc
                )

        elif "database" in exc_type.lower() or "sqlite" in exc_type.lower():
            if "timeout" in message.lower():
                return DatabaseError(
                    f"数据库操作超时: {message}",
                    ErrorCode.DATABASE_TIMEOUT,
                    details,
                    exc
                )
            elif "constraint" in message.lower():
                return DatabaseError(
                    f"数据库约束违反: {message}",
                    ErrorCode.DATABASE_CONSTRAINT_VIOLATION,
                    details,
                    exc
                )
            else:
                return DatabaseError(
                    f"数据库操作失败: {message}",
                    ErrorCode.DATABASE_QUERY_FAILED,
                    details,
                    exc
                )

        elif exc_type in ["FileNotFoundError", "OSError", "IOError"]:
            if "permission" in message.lower():
                return FileSystemError(
                    f"文件权限不足: {message}",
                    ErrorCode.FILE_PERMISSION_DENIED,
                    details,
                    exc
                )
            elif "not found" in message.lower():
                return FileSystemError(
                    f"文件未找到: {message}",
                    ErrorCode.FILE_NOT_FOUND,
                    details,
                    exc
                )
            else:
                return FileSystemError(
                    f"文件系统操作失败: {message}",
                    ErrorCode.FILE_NOT_FOUND,
                    details,
                    exc
                )

        elif exc_type in ["ValueError", "TypeError", "AttributeError"]:
            return ValidationError(
                f"参数验证失败: {message}",
                ErrorCode.INVALID_PARAMETER,
                details,
                exc
            )

        elif "timeout" in exc_type.lower() or "timeout" in message.lower():
            return MCPSandboxException(
                f"操作超时: {message}",
                ErrorCode.OPERATION_TIMEOUT,
                details,
                exc
            )

        else:
            # 默认转换为通用异常
            return MCPSandboxException(
                f"未知错误: {message}",
                ErrorCode.UNKNOWN_ERROR,
                details,
                exc
            )


def handle_exceptions(
        default_exception: Type['MCPSandboxException'] = None,
        reraise: bool = True,
        log_level: str = "ERROR",
        audit_action: Optional[str] = None
):
    """异常处理装饰器
    
    Args:
        default_exception: 默认异常类型
        reraise: 是否重新抛出异常
        log_level: 日志级别
        audit_action: 审计操作名称
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except MCPSandboxException:
                # 已经是我们的自定义异常，直接重新抛出
                if reraise:
                    raise
            except Exception as e:
                # 转换为自定义异常
                handler = ExceptionHandler()
                context = {
                    "function": func.__name__,
                    "module": func.__module__,
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                }
                custom_exception = handler.handle_exception(e, context, reraise=False)

                # 记录审计日志
                if audit_action:
                    try:
                        audit_logger = get_logger("audit")
                        audit_logger.error(
                            f"操作失败: {audit_action}",
                            extra={
                                "action": audit_action,
                                "function": f"{func.__module__}.{func.__name__}",
                                "error_type": type(custom_exception).__name__,
                                "error_code": getattr(custom_exception, 'error_code', None),
                                "original_error": str(e)
                            }
                        )
                    except Exception:
                        pass

                if reraise:
                    raise custom_exception from e
                else:
                    try:
                        logger = get_logger(func.__module__)
                        getattr(logger, log_level.lower())(
                            f"异常被捕获但未重新抛出: {custom_exception.message}",
                            extra={
                                "function": func.__name__,
                                "exception_type": type(custom_exception).__name__,
                                "suppressed": True
                            },
                            exc_info=True
                        )
                    except Exception:
                        # 如果日志记录失败，使用标准日志
                        logging.getLogger(func.__module__).error(
                            f"异常被捕获但未重新抛出: {custom_exception.message}",
                            exc_info=True
                        )
                    return None

        return wrapper

    return decorator


def safe_execute(
        func: Callable,
        *args,
        default_return=None,
        exception_types: tuple = (Exception,),
        log_errors: bool = True,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
) -> Any:
    """安全执行函数
    
    Args:
        func: 要执行的函数
        *args: 函数参数
        default_return: 异常时的默认返回值
        exception_types: 要捕获的异常类型
        log_errors: 是否记录错误日志
        context: 上下文信息
        **kwargs: 函数关键字参数
        
    Returns:
        函数执行结果或默认返回值
    """
    func_name = getattr(func, '__name__', str(func))
    module_name = getattr(func, '__module__', __name__)

    try:
        return func(*args, **kwargs)
    except exception_types as e:
        if log_errors:
            logger = logging.getLogger(module_name)

            log_extra = {
                "function": func_name,
                "exception_type": type(e).__name__,
                "safe_execution": True,
                "default_return": str(default_return),
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys())
            }

            if context:
                log_extra["context"] = context

            # 根据异常类型选择日志级别
            if isinstance(e, (ConnectionError, TimeoutError)):
                logger.warning(
                    f"函数执行遇到网络问题: {func_name}",
                    extra=log_extra,
                    exc_info=True
                )
            elif isinstance(e, (FileNotFoundError, PermissionError)):
                logger.warning(
                    f"函数执行遇到文件系统问题: {func_name}",
                    extra=log_extra,
                    exc_info=True
                )
            else:
                logger.error(
                    f"安全执行函数 {func_name} 失败: {e}",
                    extra=log_extra,
                    exc_info=True
                )

        return default_return
