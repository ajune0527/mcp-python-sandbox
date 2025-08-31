from typing import List, Dict, Any

from mcp_sandbox.core.sandbox_modules import SandboxManager


class SandboxRecords:
    """沙盒记录类 - 负责沙盒容器的记录和查询"""

    def __init__(self, manager: SandboxManager):
        """初始化沙盒记录类
        
        Args:
            manager: SandboxManager实例，用于获取容器和日志记录器
        """
        self.manager = manager
        self.logger = manager.logger

    def list_sandboxes(self) -> List[Dict[str, Any]]:
        """列出所有沙盒容器
        
        Returns:
            沙盒信息列表
        """
        sandboxes = []
        for sandbox in self.manager.sandbox_client.containers.list(all=True, filters={"label": "python-sandbox"}):
            sandbox_info = {
                "sandbox_id": sandbox.id,
                "sandbox_short_id": sandbox.short_id,
                "name": sandbox.name,
                "status": sandbox.status,
                "image": sandbox.image.tags[0] if sandbox.image.tags else sandbox.image.short_id,
                "created": sandbox.attrs["Created"],
                "last_used": self.manager.sandbox_last_used.get(sandbox.id),
            }
            sandboxes.append(sandbox_info)
        return sandboxes
