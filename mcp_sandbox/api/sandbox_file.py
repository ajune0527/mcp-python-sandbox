import io
import mimetypes
import os
import tarfile
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from mcp_sandbox.core.sandbox_modules.sandbox_core import SandboxManager
from mcp_sandbox.core.sandbox_modules.sandbox_file_ops import SandboxFileOps
from mcp_sandbox.utils.exceptions import (
    handle_exceptions, SandboxError, FileSystemError, ValidationError,
    safe_execute, ExceptionHandler
)
from mcp_sandbox.utils.logging_config import performance_monitor

# 初始化增强的日志记录器和异常处理器
exception_handler = ExceptionHandler()

router = APIRouter()

# 使用组合模式替代继承
sandbox_manager = SandboxManager()
sandbox_file_ops = SandboxFileOps(sandbox_manager)


@router.get("/sandbox/file")
@handle_exceptions(reraise=True, audit_action="get_sandbox_file")
@performance_monitor("get_sandbox_file")
def get_sandbox_file(
        # 二选一
        sandbox_id: str = Query('', description="Sandbox ID"),
        sandbox_name: str = Query('', description="Sandbox Name"),
        file_path: str = Query(...,
                               description="Absolute path to the file inside the sandbox, e.g. /app/results/foo.txt")
):
    """
    Read-only access to files inside a running sandbox.
    Returns the file content as a download if found.
    """
    try:
        # 验证输入参数 sandbox_id和sandbox_name不能同时为空
        if sandbox_id.strip() == '' and sandbox_name.strip() == '':
            raise ValidationError(
                message="沙盒ID和沙盒名称不能为空",
                details={"field": "sandbox_id、sandbox_name"}
            )

        if not file_path or not file_path.strip():
            raise ValidationError(
                message="文件路径不能为空",
                details={"field": "file_path", "sandbox_id": sandbox_id, "sandbox_name": sandbox_name}
            )

        if sandbox_id:
            return get_file_by_sandbox_id(sandbox_id, file_path)

        if sandbox_name:
            return get_file_by_sandbox_name(sandbox_name, file_path)

    except (ValidationError, SandboxError, FileSystemError):
        raise
    except Exception as e:

        raise FileSystemError(
            message=f"获取文件失败: {e}",
            details={
                "sandbox_id": sandbox_id,
                "file_path": file_path,
                "error_type": type(e).__name__
            }
        ) from e


def get_file_by_sandbox_id(sandbox_id, file_path):
    # 获取容器
    container_result = safe_execute(
        lambda: sandbox_manager.get_container_by_sandbox_id_or_name(sandbox_id),
        default_return=(None, {"message": "获取容器失败"}),
        context={"operation": "get_container", "sandbox_id": sandbox_id}
    )

    container, error = container_result
    if error:
        raise SandboxError(
            message=f"沙盒未找到: {sandbox_id}",
            details={"sandbox_id": sandbox_id, "error": error['message']}
        )

    if not container:
        raise SandboxError(
            message=f"沙盒容器未找到: {sandbox_id}",
            details={"sandbox_id": sandbox_id}
        )

    # 获取文件归档
    try:
        stream, stat = container.get_archive(file_path)

    except Exception as e:

        raise FileSystemError(
            message=f"无法访问文件: {file_path}",
            details={
                "sandbox_id": sandbox_id,
                "file_path": file_path,
                "error": str(e)
            }
        ) from e

    # 处理tar归档
    try:
        tar_bytes = io.BytesIO(b"".join(stream))
        with tarfile.open(fileobj=tar_bytes) as tar:
            members = tar.getmembers()
            if not members:
                raise FileSystemError(
                    message=f"文件未找到: {file_path}",
                    details={"sandbox_id": sandbox_id, "file_path": file_path}
                )

            rel_path = file_path.lstrip("/")
            member = next((m for m in members if m.name == rel_path), None)
            if member is None:
                basename = os.path.basename(file_path)
                member = next((m for m in members if m.name.endswith(basename)), members[0])

            fileobj = tar.extractfile(member)
            if not fileobj:
                raise FileSystemError(
                    message=f"文件提取失败: {file_path}",
                    details={
                        "sandbox_id": sandbox_id,
                        "file_path": file_path,
                        "member_name": member.name
                    }
                )

            mime_type, _ = mimetypes.guess_type(member.name)
            mime_type = mime_type or "application/octet-stream"
            headers = {"Content-Disposition": f"inline; filename={member.name}"}

            return StreamingResponse(fileobj, media_type=mime_type, headers=headers)

    except tarfile.TarError as e:

        raise FileSystemError(
            message=f"文件格式错误: {file_path}",
            details={
                "sandbox_id": sandbox_id,
                "file_path": file_path,
                "error": str(e)
            }
        ) from e


def get_file_by_sandbox_name(sandbox_name, file_path):
    # 获取容器
    container_result = safe_execute(
        lambda: sandbox_manager.get_container_by_sandbox_id_or_name(sandbox_name),
        default_return=(None, {"message": "获取容器失败"}),
        context={"operation": "get_container", "sandbox_name": sandbox_name}
    )

    container, error = container_result
    if error:
        raise SandboxError(
            message=f"沙盒未找到: {sandbox_name}",
            details={"sandbox_name": sandbox_name, "error": error['message']}
        )

    if not container:
        raise SandboxError(
            message=f"沙盒容器未找到: {sandbox_name}",
            details={"sandbox_name": sandbox_name}
        )

    # 获取文件
    try:
        # 读取项目下 data/sandbox_name下的文件
        path = Path('data')
        file_path = f"{path.absolute()}/{sandbox_name}/{file_path}"
        # 这个文件是在物理机，不需要从沙盒中读取
        with open(file_path, 'rb') as f:
            file = f.read()
            # 文件名
            filename = os.path.basename(file_path)

            mime_type, _ = mimetypes.guess_type(file_path)
            mime_type = mime_type or "application/octet-stream"
            headers = {"Content-Disposition": f"inline; filename={filename}"}

            # 内存文件流
            file = io.BytesIO(file)
            return StreamingResponse(file, media_type=mime_type, headers=headers)
    except Exception as e:

        raise FileSystemError(
            message=f"无法访问文件: {file_path}",
            details={
                "sandbox_name": sandbox_name,
                "file_path": file_path,
                "error": str(e)
            }
        ) from e
