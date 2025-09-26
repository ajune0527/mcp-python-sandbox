from fastapi import FastAPI
from mcp_sandbox.api.sandbox_file import router as sandbox_file_router
from mcp_sandbox.core.mcp_tools import SandboxToolsPlugin
from mcp_sandbox.utils.exceptions import (
    ExceptionHandler
)

# 初始化增强的日志记录器和异常处理器
exception_handler = ExceptionHandler()


def configure_app(app: FastAPI, sandbox_plugin: SandboxToolsPlugin):
    """Configure FastAPI app with routes and middleware
    
    Returns:
        The MCP app instance for lifespan configuration
    """

    # Mount sandbox file access routes
    app.include_router(sandbox_file_router)

    # 创建MCP应用实例
    mcp_app = sandbox_plugin.mcp.http_app(path="/mcp")
    # 输出所有的路由
    for route in mcp_app.routes:
        print(f"Route: {route.path}")

    # 挂载MCP服务器
    app.mount("/", mcp_app)

    # 返回MCP应用实例以便在main.py中设置lifespan
    return mcp_app
