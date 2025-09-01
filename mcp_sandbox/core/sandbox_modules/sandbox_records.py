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
            try:
                stats = sandbox.stats(stream=False)
                cpu_percent = self.get_container_cpu_percent(stats)
                sandbox_info = {
                    "sandbox_id": sandbox.id,
                    "sandbox_short_id": sandbox.short_id,
                    "name": sandbox.name,
                    "status": sandbox.status,
                    "image": sandbox.image.tags[0] if sandbox.image.tags else sandbox.image.short_id,
                    "created": sandbox.attrs["Created"],
                    "last_used": self.manager.sandbox_last_used.get(sandbox.id),
                    "cpu": round(cpu_percent, 2),
                }
                sandboxes.append(sandbox_info)
            except Exception as e:
                self.logger.info(f"[跳过] 获取容器 {sandbox.name} 统计信息失败: {e}")

        return sandboxes

    def get_container_cpu_percent(self, stats):
        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
            stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - \
            stats['precpu_stats']['system_cpu_usage']
        if system_delta > 0 and cpu_delta > 0:
            return (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage'].get('percpu_usage', [])) * 100.0
        return 0.0
