import uvicorn
import signal
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mcp_sandbox.api.routes import configure_app
from mcp_sandbox.core.mcp_tools import SandboxToolsPlugin
from mcp_sandbox.utils.config import logger, HOST, PORT
from mcp_sandbox.utils.task_manager import PeriodicTaskManager

# 全局变量，用于在信号处理函数中访问
shutdown_event = None


# 信号处理函数
def signal_handler(sig, frame):
    """处理终止信号，确保优雅关闭"""
    logger.info(f"接收到信号 {sig}，开始优雅关闭...")

    # 停止所有后台任务
    PeriodicTaskManager.stop_all_tasks()

    # 如果使用了shutdown_event，设置它
    if shutdown_event:
        shutdown_event.set()

    logger.info("清理完成，准备退出")
    sys.exit(0)


def main():
    """Main entry point for the application"""
    # 注册信号处理函数
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill

    # 初始化沙箱插件
    sandbox_plugin = SandboxToolsPlugin()

    # Create FastAPI app
    app = FastAPI(title="MCP Sandbox")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Adjust in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 配置应用并获取MCP应用实例
    mcp_app = configure_app(app, sandbox_plugin)

    # 设置FastAPI应用的lifespan
    app.router.lifespan_context = mcp_app.lifespan
    
    # 输出所有的路由
    for route in app.routes:
        print(f"Route: {route.path}")

    # 设置uvicorn配置，确保正确处理信号
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
        timeout_graceful_shutdown=10,
        reload=False,  # 禁用热重载以避免信号处理问题
        use_colors=True
    )


if __name__ == "__main__":
    main()
