# MCP Sandbox - 安全的LLM代码执行沙盒

## 项目简介

MCP Sandbox 是一个基于 Docker 的安全代码执行沙盒系统，专为大语言模型（LLM）提供安全、隔离的 Python 代码执行环境。该项目通过 Model Context Protocol (MCP) 协议暴露沙盒功能，支持动态创建、管理和销毁沙盒环境。

## 主要功能

### 🔒 安全沙盒执行
- **Docker 容器隔离**：每个沙盒运行在独立的 Docker 容器中，确保代码执行的安全性
- **非 root 用户执行**：容器内使用非特权用户执行代码，降低安全风险
- **资源限制**：可配置的内存和 CPU 限制，防止资源滥用

### 🐍 Python 代码执行
- **动态代码执行**：支持实时执行 Python 代码并返回结果
- **包管理**：支持在沙盒中安装和管理 Python 包
- **文件操作**：支持文件的创建、读取和下载
- **终端命令**：支持在沙盒中执行终端命令

### 🌐 Web API 接口
- **FastAPI 框架**：基于 FastAPI 构建的高性能 Web 服务
- **RESTful API**：提供标准的 REST API 接口
- **MCP 协议支持**：完整支持 Model Context Protocol
- **CORS 支持**：支持跨域请求

### 📁 文件管理
- **文件上传下载**：支持向沙盒上传文件和从沙盒下载文件
- **文件链接生成**：自动生成文件访问链接
- **目录浏览**：支持浏览沙盒内的文件结构

## 技术架构

### 核心组件

```
mcp_sandbox/
├── api/                    # Web API 层
│   ├── routes.py          # 路由配置
│   └── sandbox_file.py    # 文件操作 API
├── core/                  # 核心业务逻辑
│   ├── mcp_tools.py       # MCP 工具插件
│   └── sandbox_modules/   # 沙盒模块
│       ├── sandbox_core.py      # 沙盒核心管理
│       ├── sandbox_execution.py # 代码执行
│       ├── sandbox_file_ops.py  # 文件操作
│       ├── sandbox_package.py   # 包管理
│       └── sandbox_records.py   # 记录管理
├── models.py              # 数据模型
└── utils/                 # 工具模块
    ├── config.py          # 配置管理
    ├── exceptions.py      # 异常处理
    ├── logging_config.py  # 日志配置
    └── task_manager.py    # 任务管理
```

### 技术栈

- **后端框架**：FastAPI 0.115.12+
- **容器化**：Docker
- **协议支持**：FastMCP 2.2.0+
- **数据验证**：Pydantic 2.11.3+
- **包管理**：UV（Python 包管理器）
- **日志系统**：结构化日志记录
- **配置管理**：TOML 配置文件

### 架构特点

1. **模块化设计**：采用组合模式，各功能模块独立且可复用
2. **线程安全**：使用 RLock 确保多线程环境下的安全性
3. **异常处理**：完善的异常处理机制和错误恢复
4. **性能监控**：内置性能监控和日志记录
5. **配置驱动**：通过配置文件灵活控制系统行为

## 安装与使用

### 环境要求

- Python 3.12+
- Docker
- UV 包管理器

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd simple
```

2. **安装依赖**
```bash
uv sync
```

3. **构建 Docker 镜像**
```bash
docker build -t python-sandbox:latest -f sandbox_images/Dockerfile .
```

4. **配置系统**

编辑 `config.toml` 文件，根据需要调整配置：

```toml
[server]
host = "0.0.0.0"
port = 8000

[docker]
default_image = "python-sandbox:latest"
open_mount_directory = true
container_work_dir = "/app/results"

[logging]
level = "INFO"
log_file = "./logs/mcp_sandbox.log"
```

### 启动服务

```bash
# 使用 UV 运行
uv run main.py

# 或者使用项目脚本
uv run mcp-sandbox
```

服务启动后，可以通过以下地址访问：
- **API 文档**：http://localhost:8000/docs
- **MCP 端点**：http://localhost:8000/mcp

### 基本使用示例

#### 1. 创建沙盒
```python
import requests

# 创建新沙盒
response = requests.post("http://localhost:8000/mcp/tools/create_sandbox")
sandbox_info = response.json()
sandbox_id = sandbox_info["sandbox_id"]
```

#### 2. 执行 Python 代码
```python
# 执行代码
code = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 10, 100)
y = np.sin(x)

plt.figure(figsize=(10, 6))
plt.plot(x, y)
plt.title('Sine Wave')
plt.savefig('sine_wave.png')
plt.show()

print("图表已生成")
"""

response = requests.post(
    "http://localhost:8000/mcp/tools/execute_python_code",
    json={"sandbox_id": sandbox_id, "code": code}
)
result = response.json()
```

#### 3. 下载生成的文件
```python
# 获取文件链接
file_url = f"http://localhost:8000/sandbox/file?sandbox_id={sandbox_id}&file_path=/app/results/sine_wave.png"

# 下载文件
file_response = requests.get(file_url)
with open("downloaded_sine_wave.png", "wb") as f:
    f.write(file_response.content)
```

## API 文档

### MCP 工具

| 工具名称 | 描述 | 参数 |
|---------|------|------|
| `create_sandbox` | 创建新的沙盒环境 | `name` (可选): 沙盒名称 |
| `list_sandboxes` | 列出所有沙盒 | 无 |
| `execute_python_code` | 执行 Python 代码 | `sandbox_id`: 沙盒ID, `code`: Python代码 |
| `execute_terminal_command` | 执行终端命令 | `sandbox_id`: 沙盒ID, `command`: 命令 |
| `install_packages_in_sandbox` | 安装 Python 包 | `sandbox_id`: 沙盒ID, `package_names`: 包名列表 |
| `upload_file_to_sandbox` | 上传文件到沙盒 | `sandbox_id`: 沙盒ID, `local_file_path`: 本地文件路径 |

### REST API

- **GET** `/sandbox/file` - 下载沙盒中的文件
  - 参数：`sandbox_id` 或 `sandbox_name`, `file_path`
- **GET** `/docs` - API 文档
- **POST** `/mcp/*` - MCP 协议端点

## 配置说明

### 服务器配置 (`config.toml`)

```toml
[server]
host = "0.0.0.0"          # 服务监听地址
port = 8000               # 服务端口

[docker]
default_image = "python-sandbox:latest"  # 默认 Docker 镜像
open_mount_directory = true              # 是否开启目录挂载
container_work_dir = "/app/results"      # 容器工作目录

[logging]
level = "INFO"                           # 日志级别
log_file = "./logs/mcp_sandbox.log"      # 日志文件路径
use_structured_format = true            # 是否使用结构化日志

[mirror]
pypi_index_url = "https://pypi.tuna.tsinghua.edu.cn/simple"  # PyPI 镜像源
```

## 安全特性

1. **容器隔离**：每个沙盒运行在独立的 Docker 容器中
2. **非特权用户**：容器内使用 `python` 用户执行代码，非 root 权限
3. **资源限制**：可配置内存和 CPU 限制
4. **网络隔离**：容器网络与宿主机隔离
5. **文件系统隔离**：容器文件系统与宿主机隔离
6. **异常处理**：完善的错误处理和恢复机制

## 开发指南

### 项目结构

项目采用模块化设计，主要模块包括：

- **API 层**：处理 HTTP 请求和响应
- **核心层**：实现沙盒管理和代码执行逻辑
- **工具层**：提供配置、日志、异常处理等工具

### 扩展开发

1. **添加新的 MCP 工具**：在 `mcp_tools.py` 中注册新工具
2. **扩展沙盒功能**：在 `sandbox_modules` 中添加新模块
3. **自定义配置**：修改 `config.toml` 和 `config.py`

### 测试

```bash
# 运行测试
uv run pytest

# 代码格式检查
uv run ruff check

# 代码格式化
uv run ruff format
```

## 许可证

本项目采用开源许可证，具体许可证信息请查看 LICENSE 文件。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进项目。在提交代码前，请确保：

1. 代码符合项目的编码规范
2. 添加必要的测试用例
3. 更新相关文档

## 联系方式

如有问题或建议，请通过以下方式联系：

- 提交 GitHub Issue
- 发送邮件至项目维护者

---

**注意**：本项目仍在积极开发中，API 可能会发生变化。建议在生产环境使用前进行充分测试。