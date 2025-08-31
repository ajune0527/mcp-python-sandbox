"""配置管理模块

提供应用程序的配置加载、验证和访问功能。
支持从TOML文件加载配置，并提供默认配置作为后备。
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import tomli
except ImportError:
    # 兼容性处理：如果tomli不可用，尝试使用tomllib (Python 3.11+)
    try:
        import tomllib as tomli  # type: ignore
    except ImportError:
        raise ImportError("需要安装tomli库或使用Python 3.11+")


class ConfigManager:
    """配置管理器类
    
    负责加载、验证和提供配置访问接口。
    """

    def __init__(self, config_file: Optional[Path] = None) -> None:
        """初始化配置管理器
        
        Args:
            config_file: 配置文件路径，默认为当前目录下的config.toml
        """
        self.config_file = config_file or Path("config.toml").resolve()
        self._config: Dict[str, Any] = {}
        self._load_config()

    @property
    def default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "server": {
                "host": "0.0.0.0",
                "port": 8000,
                "reset_all_containers": False,  # 是否在启动时重置所有容器
            },
            "auth": {
                "require_auth": False,
                "default_user_id": "root",
                "user_sandbox_limit": 3,  # 每个用户最多可创建的沙盒数量
            },
            "docker": {
                "default_image": "python-sandbox:latest",
                "dockerfile_path": "sandbox_images/Dockerfile",
                "check_dockerfile_changes": True,
                "build_info_file": ".docker_build_info",
                "user_only_one_container": False,  # 是否限制每个用户只能创建一个容器
            },
            "logging": {
                "level": "info",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "log_file": "mcp_sandbox.log",
            },
            "mirror": {
                "pypi_index_url": "https://pypi.org/simple/",  # 添加默认PyPI镜像URL
            },
        }

    def _load_config(self) -> None:
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "rb") as f:
                    loaded_config = tomli.load(f)
                # 深度合并配置，确保所有默认值都存在
                self._config = self._deep_merge(self.default_config, loaded_config)
                logging.info(f"已从 {self.config_file} 加载配置")
            else:
                self._config = self.default_config.copy()
                logging.warning(f"配置文件 {self.config_file} 不存在，使用默认配置")
        except Exception as e:
            logging.error(f"加载配置文件失败: {e}，使用默认配置")
            self._config = self.default_config.copy()

    def _deep_merge(self, default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """深度合并两个字典
        
        Args:
            default: 默认配置字典
            override: 覆盖配置字典
            
        Returns:
            合并后的配置字典
        """
        result = default.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, key_path: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key_path: 配置键路径，支持点分隔的嵌套路径，如 'server.host'
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        keys = key_path.split('.')
        value = self._config

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self._config[key]

    def __contains__(self, key: str) -> bool:
        """支持 in 操作符"""
        return key in self._config


# 创建全局配置管理器实例
config_manager = ConfigManager()
config = config_manager  # 保持向后兼容性

# 提取配置值（支持环境变量覆盖）
HOST = os.environ.get("APP_HOST", config_manager.get("server.host", "0.0.0.0"))
PORT = int(os.environ.get("APP_PORT", config_manager.get("server.port", 8000)))
DEFAULT_DOCKER_IMAGE = config_manager.get("docker.default_image", "python-sandbox:latest")
OPEN_MOUNT_DIRECTORY = config_manager.get("docker.open_mount_directory", False)
DOCKER_MEM_LIMIT = config_manager.get("docker.mem_limit", '1g')
DOCKER_MEM_SWAP_LIMIT = config_manager.get("docker.memswap_limit", '1g')
DEFAULT_CONTAINER_WORK_DIR = config_manager.get("docker.container_work_dir", "/app/results")
DEFAULT_LOG_FILE = config_manager.get("logging.log_file", "./logs/mcp_sandbox.log")

# PyPI镜像配置
PYPI_INDEX_URL = config_manager.get("mirror.pypi_index_url", "https://pypi.org/simple/")

# 文件访问基础URL
BASE_URL = f"http://{HOST}:{PORT}/static/"


class ColorFormatter(logging.Formatter):
    """彩色日志格式化器
    
    为不同级别的日志消息添加颜色，提升控制台输出的可读性。
    """

    COLOR_MAP = {
        logging.DEBUG: "\033[37m",  # 白色
        logging.INFO: "\033[32m",  # 绿色
        logging.WARNING: "\033[33m",  # 黄色
        logging.ERROR: "\033[31m",  # 红色
        logging.CRITICAL: "\033[41m",  # 红色背景
    }
    RESET_SEQ = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录
        
        Args:
            record: 日志记录对象
            
        Returns:
            格式化后的彩色日志字符串
        """
        msg = super().format(record)
        color = self.COLOR_MAP.get(record.levelno, self.RESET_SEQ)
        return f"{color}{msg}{self.RESET_SEQ}"


def setup_logger(name: str = "MCP_SANDBOX") -> logging.Logger:
    """设置并配置日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        配置好的日志记录器实例
    """
    from .logging_config import logging_config

    # 获取日志配置
    log_level = config_manager.get("logging.level", "INFO")
    use_structured_format = config_manager.get("logging.use_structured_format", True)
    max_file_size = config_manager.get("logging.max_file_size", 10 * 1024 * 1024)  # 默认10MB
    backup_count = config_manager.get("logging.backup_count", 5)
    console_output = config_manager.get("logging.console_output", True)

    # 使用统一的日志配置管理器
    return logging_config.setup_logging(
        level=log_level,
        log_file=DEFAULT_LOG_FILE,
        max_file_size=max_file_size,
        backup_count=backup_count,
        use_structured_format=use_structured_format,
        console_output=console_output,
        logger_name=name
    )


# 创建全局日志记录器
logger = setup_logger()
