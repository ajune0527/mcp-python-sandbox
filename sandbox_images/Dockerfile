FROM python:3.12-slim

WORKDIR /app

# 安装基本工具和中文字体
RUN apt-get update && apt-get install -y \
    curl \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install uv

# 创建非 root 用户
RUN groupadd -r python && useradd -r -g python -d /home/python -m python

# 为额外的包安装提供目录
RUN mkdir -p /app/results && chown -R python:python /app

# 设置安全执行用户
USER python

# 创建并激活 uv 虚拟环境
RUN uv venv && \
    echo 'source .venv/bin/activate' >> /home/python/.bashrc

ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# 设置工作目录为结果目录
WORKDIR /app/results

# 容器入口点 - 使用 sleep infinity 保持容器运行
CMD ["sleep", "infinity"]
