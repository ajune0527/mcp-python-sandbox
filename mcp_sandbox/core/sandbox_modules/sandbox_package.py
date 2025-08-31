from typing import Dict, Any, List, Optional
import threading
from datetime import datetime

from mcp_sandbox.core.sandbox_modules import SandboxManager
from mcp_sandbox.utils.config import PYPI_INDEX_URL


class SandboxPackage:
    """沙盒包管理类 - 负责沙盒环境中的包安装和管理"""

    def __init__(self, manager: SandboxManager):
        """初始化沙盒包管理类
        
        Args:
            manager: SandboxManager实例，用于获取容器和日志记录器
        """
        self.manager = manager
        self.logger = manager.logger

    def install_packages(self, sandbox_id: str, package_names: List[str]) -> Dict[str, Any]:
        """批量安装多个包到沙盒环境
        
        Args:
            sandbox_id: 沙盒ID
            package_names: 要安装的包名列表
            
        Returns:
            包含安装结果的字典
        """
        # 验证沙盒是否存在
        error = self.manager.verify_sandbox_exists(sandbox_id)
        if error:
            return error

        # 将包名列表转换为空格分隔的字符串
        packages_str = " ".join(package_names)
        status_key = f"{sandbox_id}:batch_install"

        try:
            with self.manager.get_running_sandbox(sandbox_id) as sandbox:
                pip_index_url = PYPI_INDEX_URL
                pip_index_opt = f" --index-url {pip_index_url}" if pip_index_url else ""
                self.logger.info(f"正在安装包: {packages_str}，使用pip索引URL: {pip_index_url}")

                # 执行批量安装命令
                exec_result = sandbox.exec_run(
                    cmd=f"uv pip install{pip_index_opt} {packages_str}",
                    stdout=True,
                    stderr=True,
                    privileged=False
                )

                exit_code = exec_result.exit_code
                output = exec_result.output.decode('utf-8')
                self.logger.info(f"批量包安装输出: {output}")
                self.logger.info(f"退出码: {exit_code}")

                # 更新每个包的安装状态
                for package_name in package_names:
                    individual_status_key = f"{sandbox_id}:{package_name}"

                    if exit_code == 0:
                        status = {
                            "status": "success",
                            "message": f"成功安装 {package_name}",
                            "complete": True,
                            "success": True,
                            "end_time": datetime.now()
                        }
                    else:
                        status = {
                            "status": "failed",
                            "message": f"安装 {package_name} 失败: {output}",
                            "stderr": output,
                            "complete": True,
                            "success": False,
                            "end_time": datetime.now()
                        }

                    self.manager.package_install_status[individual_status_key] = status

                # 返回批量安装的总体状态
                if exit_code == 0:
                    status = {
                        "status": "success",
                        "message": f"成功安装包: {packages_str}",
                        "complete": True,
                        "success": True,
                        "end_time": datetime.now(),
                        "packages": package_names
                    }
                else:
                    status = {
                        "status": "failed",
                        "message": f"安装包失败: {output}",
                        "stderr": output,
                        "complete": True,
                        "success": False,
                        "end_time": datetime.now(),
                        "packages": package_names
                    }

                self.manager.package_install_status[status_key] = status
                return status
        except Exception as e:
            self.logger.error(f"为沙盒 {sandbox_id} 安装包失败: {e}", exc_info=True)
            error_message = str(e)
            if hasattr(e, 'stderr') and e.stderr:
                stderr = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else str(e.stderr)
                error_message = f"{error_message}\n详细信息: {stderr}"

            status = {
                "status": "failed",
                "message": f"安装包失败: {error_message}",
                "stderr": error_message,
                "complete": True,
                "success": False,
                "end_time": datetime.now(),
                "packages": package_names
            }
            self.manager.package_install_status[status_key] = status
            return status

    def check_packages_status(self, sandbox_id: str, package_names: List[str]) -> Dict[str, Any]:
        """检查多个包在沙盒中的安装状态
        
        Args:
            sandbox_id: 沙盒ID
            package_names: 要检查的包名列表
            
        Returns:
            包含包状态的字典
        """
        # 验证沙盒是否存在
        error = self.manager.verify_sandbox_exists(sandbox_id)
        if error:
            return error

        try:
            with self.manager.get_running_sandbox(sandbox_id) as sandbox:
                # 使用pip list命令获取已安装的包
                exec_result = sandbox.exec_run(
                    cmd="pip list --format=json",
                    stdout=True,
                    stderr=True,
                    privileged=False
                )

                if exec_result.exit_code != 0:
                    return {
                        "status": "failed",
                        "message": "获取已安装包列表失败",
                        "stderr": exec_result.output.decode('utf-8'),
                        "packages": {}
                    }

                import json
                try:
                    installed_packages = json.loads(exec_result.output.decode('utf-8'))
                    installed_dict = {pkg["name"].lower(): pkg["version"] for pkg in installed_packages}
                except json.JSONDecodeError:
                    return {
                        "status": "failed",
                        "message": "解析已安装包列表失败",
                        "stderr": exec_result.output.decode('utf-8'),
                        "packages": {}
                    }

                # 检查每个包的状态
                package_status = {}
                for package_name in package_names:
                    package_lower = package_name.lower()
                    if package_lower in installed_dict:
                        package_status[package_name] = {
                            "installed": True,
                            "version": installed_dict[package_lower]
                        }
                    else:
                        package_status[package_name] = {
                            "installed": False
                        }

                return {
                    "status": "success",
                    "message": "成功获取包状态",
                    "packages": package_status
                }

        except Exception as e:
            self.logger.error(f"检查沙盒 {sandbox_id} 中的包状态失败: {e}", exc_info=True)
            return {
                "status": "failed",
                "message": f"检查包状态失败: {str(e)}",
                "packages": {}
            }
