from typing import Dict, Any, List, Optional
from fastmcp import FastMCP
from mcp_sandbox.core import sandbox_modules as sandbox
from mcp_sandbox.utils.config import DEFAULT_DOCKER_IMAGE


class SandboxEnvironment:
    """沙盒环境 - 集成所有沙盒功能的主类"""

    def __init__(self, base_image: str = DEFAULT_DOCKER_IMAGE):
        """初始化沙盒环境
        
        Args:
            base_image: 基础Docker镜像名称
        """
        # 使用组合模式替代继承
        self.manager = sandbox.SandboxManager(base_image=base_image)
        self.file_ops = sandbox.SandboxFileOps(self.manager)
        self.package = sandbox.SandboxPackage(self.manager)
        self.records = sandbox.SandboxRecords(self.manager)
        self.execution = sandbox.SandboxExecution(self.manager, self.file_ops)

    # 代理方法 - 沙盒管理
    def create_sandbox(self, name: Optional[str] = None) -> Dict[str, Any]:
        return self.manager.create_sandbox(name)

    # 代理方法 - 文件操作
    def list_files_in_sandbox(self, sandbox_id: str, directory: str = "/app/results", with_stat: bool = False) -> List:
        return self.file_ops.list_files_in_sandbox(sandbox_id, directory, with_stat)

    def get_file_link(self, sandbox_id: str, file_path: str) -> str:
        return self.file_ops.get_file_link(sandbox_id, file_path)

    def get_machine_file_link(self, sandbox_name: str, file_path: str) -> str:
        return self.file_ops.get_machine_file_link(sandbox_name, file_path)

    def upload_file_to_sandbox(self, sandbox_id: str, local_file_path: str, dest_path: str = "/app/results") -> Dict[
        str, Any]:
        return self.file_ops.upload_file_to_sandbox(sandbox_id, local_file_path, dest_path)

    # 代理方法 - 包管理
    def install_packages(self, sandbox_id: str, package_names: List[str]) -> Dict[str, Any]:
        return self.package.install_packages(sandbox_id, package_names)

    def check_packages_status(self, sandbox_id: str, package_names: List[str]) -> Dict[str, Any]:
        return self.package.check_packages_status(sandbox_id, package_names)

    # 代理方法 - 记录查询
    def list_sandboxes(self) -> List[Dict[str, Any]]:
        return self.records.list_sandboxes()

    # 代理方法 - 代码执行
    def execute_python_code(self, sandbox_id: str, code: str) -> Dict[str, Any]:
        return self.execution.execute_python_code(sandbox_id, code)

    def execute_terminal_command(self, sandbox_id: str, command: str) -> Dict[str, Any]:
        return self.execution.execute_terminal_command(sandbox_id, command)


class SandboxToolsPlugin:
    """将沙盒操作作为MCP工具暴露，用于Python代码执行。"""

    def __init__(self, base_image: str = DEFAULT_DOCKER_IMAGE):
        self.sandbox_env = SandboxEnvironment(base_image=base_image)
        self.mcp = FastMCP("Python Sandbox Executor")
        self.user_context = {}
        self._register_tools()

    def _register_tools(self):
        """注册所有MCP工具"""

        @self.mcp.tool(
            name="list_sandboxes",
            description="列出所有现有的Python沙盒及其状态。每个项目还包括已安装的Python包。"
        )
        def list_sandboxes() -> list:
            return self.sandbox_env.list_sandboxes()

        @self.mcp.tool(
            name="create_sandbox",
            description="创建一个新的Python沙盒并返回其ID以供后续操作。可选参数: name (string) - 沙盒的自定义名称"
        )
        def create_sandbox(name: Optional[str] = None) -> dict:
            return self.sandbox_env.create_sandbox(name)

        @self.mcp.tool(
            name="install_packages_in_sandbox",
            description="在指定的沙盒中安装多个Python包。参数: sandbox_id (string), package_names (字符串列表)"
        )
        def install_packages_in_sandbox(sandbox_id: str, package_names: List[str]) -> Dict[str, Any]:
            return self.sandbox_env.install_packages(sandbox_id, package_names)

        @self.mcp.tool(
            name="check_packages_installation_status",
            description="检查沙盒中多个包的安装状态。参数: sandbox_id (string), package_names (字符串列表)"
        )
        def check_packages_installation_status(sandbox_id: str, package_names: List[str]) -> Dict[str, Any]:
            return self.sandbox_env.check_packages_status(sandbox_id, package_names)

        @self.mcp.tool(
            name="execute_python_code",
            description="在沙盒中执行Python代码并返回结果，包括生成文件的链接。参数: sandbox_id (string) - 要使用的沙盒ID, code (string) - 要执行的Python代码"
        )
        def execute_python_code(sandbox_id: str, code: str) -> Dict[str, Any]:
            return self.sandbox_env.execute_python_code(sandbox_id, code)

        @self.mcp.tool(
            name="execute_terminal_command",
            description="在指定的沙盒中执行终端命令。参数: sandbox_id (string), command (string)。返回stdout、stderr、exit_code。"
        )
        def execute_terminal_command(sandbox_id: str, command: str) -> Dict[str, Any]:
            return self.sandbox_env.execute_terminal_command(sandbox_id, command)

        @self.mcp.tool(
            name="upload_file_to_sandbox",
            description="将本地文件上传到指定的沙盒。参数: sandbox_id (string), local_file_path (string), dest_path (string, 可选, 默认: /app/results)。"
        )
        def upload_file_to_sandbox(sandbox_id: str, local_file_path: str, dest_path: str = "/app/results") -> dict:
            return self.sandbox_env.upload_file_to_sandbox(sandbox_id, local_file_path, dest_path)
