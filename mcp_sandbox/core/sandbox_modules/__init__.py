# 为了保持向后兼容性，从新的模块结构中导入类

# 导入新的类结构
from .sandbox_core import SandboxManager
from .sandbox_file_ops import SandboxFileOps
from .sandbox_package import SandboxPackage
from .sandbox_records import SandboxRecords
from .sandbox_execution import SandboxExecution

# 导出类，保持旧的导入路径可用
__all__ = [
    'SandboxManager',
    'SandboxFileOps',
    'SandboxPackage',
    'SandboxRecords',
    'SandboxExecution',
]
