from typing import List, Optional, Dict, Any
import tarfile
import io
from pathlib import Path

from mcp_sandbox.core.sandbox_modules import SandboxManager


class SandboxFileOps:
    """沙盒文件操作类 - 负责沙盒内文件的管理和操作"""

    def __init__(self, manager: SandboxManager):
        """初始化沙盒文件操作类
        
        Args:
            manager: SandboxManager实例，用于获取容器和日志记录器
        """
        self.manager = manager
        self.logger = manager.logger

    def list_files_in_sandbox(self, sandbox_id: str, directory: str = "/app/results", with_stat: bool = False) -> List:
        """列出沙盒中指定目录下的文件
        
        Args:
            sandbox_id: 沙盒ID
            directory: 要列出文件的目录路径
            with_stat: 是否包含文件状态信息
            
        Returns:
            文件路径列表或(文件路径, 创建时间)元组列表
        """
        try:
            container, error = self.manager.get_container_by_sandbox_id_or_name(sandbox_id)
            if error:
                self.logger.error(f"获取沙盒 {sandbox_id} 的容器失败: {error['message']}")
                return []

            if not container:
                self.logger.error(f"未找到沙盒 {sandbox_id} 的容器")
                return []

            exec_result = container.exec_run(f"ls -1 {directory}")
            if exec_result.exit_code != 0:
                return []

            files = exec_result.output.decode().splitlines()
            full_paths = [f"{directory.rstrip('/')}/{f}" for f in files]

            if with_stat:
                stat_files = []
                for f in full_paths:
                    stat_result = container.exec_run(f'stat -c "%n|%Z" "{f}"')
                    if stat_result.exit_code == 0:
                        parts = stat_result.output.decode().strip().split("|", 1)
                        if len(parts) == 2:
                            stat_files.append((parts[0], int(parts[1])))
                return stat_files
            else:
                return full_paths
        except Exception as e:
            self.logger.error(f"列出沙盒 {sandbox_id} 中的文件失败: {e}")
            return []

    @staticmethod
    def get_file_link(sandbox_id: str, file_path: str) -> str:
        """获取沙盒文件的访问链接
        
        Args:
            sandbox_id: 沙盒ID
            file_path: 文件路径
            
        Returns:
            文件访问链接
        """
        from mcp_sandbox.utils.config import config

        base_url = getattr(config, "BASE_URL", None) or "http://localhost:8000"
        url = f"{base_url}/sandbox/file?sandbox_id={sandbox_id}&file_path={file_path}"

        return url

    @staticmethod
    def get_machine_file_link(sandbox_name: str, file_path: str) -> str:
        """获取机器文件的访问链接
        
        Args:
            sandbox_name: 沙盒名称
            file_path: 文件路径
            
        Returns:
            文件访问链接
        """
        from mcp_sandbox.utils.config import config

        base_url = getattr(config, "BASE_URL", None) or "http://localhost:8000"
        file_name = file_path.split("/")[-1]
        url = f"{base_url}/sandbox/file?sandbox_name={sandbox_name}&file_path={file_name}"

        return url

    def upload_file_to_sandbox(self, sandbox_id: str, local_file_path: str, dest_path: str = "/app/results") -> Dict[
        str, Any]:
        """上传文件到沙盒
        
        Args:
            sandbox_id: 沙盒ID
            local_file_path: 本地文件路径
            dest_path: 目标路径
            
        Returns:
            上传结果字典
        """
        error = self.manager.verify_sandbox_exists(sandbox_id)
        if error:
            return error
        try:
            with self.manager.get_running_sandbox(sandbox_id) as sandbox:
                local_file = Path(local_file_path)
                if not local_file.exists():
                    return {"error": True, "message": f"本地文件不存在: {local_file_path}"}
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    tar.add(str(local_file), arcname=local_file.name)
                tar_stream.seek(0)
                sandbox.put_archive(dest_path, tar_stream.read())
                return {"success": True,
                        "message": f"已上传 {local_file.name} 到沙盒 {sandbox_id} 的 {dest_path} 目录"}
        except Exception as e:
            self.logger.error(f"上传文件到沙盒 {sandbox_id} 失败: {e}", exc_info=True)
            return {"error": True, "message": str(e)}
