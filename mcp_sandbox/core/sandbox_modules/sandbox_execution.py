from typing import Dict, Any
import time
from mcp_sandbox.utils.config import DEFAULT_CONTAINER_WORK_DIR


class SandboxExecution:
    """沙盒执行类 - 负责在沙盒中执行代码和命令"""

    def __init__(self, manager, file_ops):
        """初始化沙盒执行类
        
        Args:
            manager: SandboxManager实例，用于获取容器和日志记录器
            file_ops: SandboxFileOps实例，用于文件操作
        """
        self.manager = manager
        self.file_ops = file_ops
        self.logger = manager.logger

    def execute_python_code(self, sandbox_id: str, code: str) -> Dict[str, Any]:
        """在沙盒中执行Python代码
        
        Args:
            sandbox_id: 沙盒ID
            code: 要执行的Python代码
            
        Returns:
            执行结果字典
        """
        # 验证沙盒是否存在
        error = self.manager.verify_sandbox_exists(sandbox_id)
        if error:
            return error

        start_ts = int(time.time())
        self.logger.info("正在执行代码:")
        self.logger.info("=" * 50)
        self.logger.info(code)
        self.logger.info("=" * 50)
        self.logger.info(f"在沙盒 {sandbox_id} 中运行代码")

        # 强制睡一秒，保证可以拿到文件
        time.sleep(1)

        try:
            with self.manager.get_running_sandbox(sandbox_id) as sandbox:
                temp_code_file = "/tmp/code_to_run.py"
                write_code_cmd = f"cat > {temp_code_file} << 'EOL'\n{code}\nEOL"
                write_result = sandbox.exec_run(
                    cmd=["sh", "-c", write_code_cmd],
                    workdir=DEFAULT_CONTAINER_WORK_DIR,
                    privileged=False
                )

                if write_result.exit_code != 0:
                    self.logger.error(f"写入代码到沙盒失败: {write_result.output.decode('utf-8')}")
                    return {
                        "error": "准备代码执行失败",
                        "stdout": "",
                        "stderr": write_result.output.decode('utf-8'),
                        "exit_code": write_result.exit_code,
                        "files": [],
                        "file_links": []
                    }

                exec_result = sandbox.exec_run(
                    cmd=["python", temp_code_file],
                    workdir=DEFAULT_CONTAINER_WORK_DIR,
                    stdout=True,
                    stderr=True,
                    demux=True,
                    privileged=False
                )

                exit_code = exec_result.exit_code
                stdout_bytes, stderr_bytes = exec_result.output
                stdout = stdout_bytes.decode('utf-8') if stdout_bytes else ""
                stderr = stderr_bytes.decode('utf-8') if stderr_bytes else ""

                # 删除临时代码文件
                sandbox.exec_run(cmd=["rm", "-f", temp_code_file], privileged=False)

                # 获取新生成的文件
                all_files = self.file_ops.list_files_in_sandbox(sandbox_id, with_stat=True)
                new_files = [f for f, ctime in all_files if ctime >= start_ts]
                file_links = [self.file_ops.get_file_link(sandbox_id, f) for f in new_files]
                machine_file_links = [self.file_ops.get_machine_file_link(sandbox.name, f) for f in new_files]

                self.logger.info("执行结果:")
                self.logger.info(f"退出码: {exit_code}")
                if stdout:
                    self.logger.info("标准输出:")
                    self.logger.info(stdout)
                if stderr:
                    self.logger.warning("标准错误:")
                    self.logger.warning(stderr)

                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "files": new_files,
                    "file_links": file_links,
                    "machine_file_links": machine_file_links
                }
        except ValueError as e:
            return {
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1,
                "files": [],
                "file_links": []
            }
        except Exception as e:
            self.logger.error(f"在沙盒 {sandbox_id} 中运行代码失败: {e}", exc_info=True)
            error_message = str(e)
            if hasattr(e, 'stderr') and e.stderr:
                stderr = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else str(e.stderr)
                error_message = f"{error_message}\n详细信息: {stderr}"
            return {
                "error": error_message,
                "stdout": "",
                "stderr": error_message,
                "exit_code": 1,
                "files": [],
                "file_links": []
            }

    def execute_terminal_command(self, sandbox_id: str, command: str) -> Dict[str, Any]:
        """在指定的沙盒中执行终端命令
        
        Args:
            sandbox_id: 沙盒ID
            command: 要执行的命令
            
        Returns:
            包含stdout、stderr和exit_code的字典
        """
        # 验证沙盒是否存在
        error = self.manager.verify_sandbox_exists(sandbox_id)
        if error:
            return {
                "stdout": "",
                "stderr": error.get("message", "沙盒不存在"),
                "exit_code": -1
            }

        try:
            with self.manager.get_running_sandbox(sandbox_id) as container:
                self.logger.info(f"在沙盒 {sandbox_id} 中执行命令: {command}")
                exec_result = container.exec_run(command, stdout=True, stderr=True, stdin=False, tty=False, demux=True)
                exit_code = exec_result.exit_code
                stdout_bytes, stderr_bytes = exec_result.output

                stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
                stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""

                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code
                }
        except Exception as e:
            self.logger.error(f"在沙盒 {sandbox_id} 中执行命令出错: {e}", exc_info=True)
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1
            }
