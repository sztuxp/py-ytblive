# 使用官方轻量级 Python 镜像
FROM python:3.11-slim

# 设置环境变量，确保 Python 输出不被缓存，实时显示日志
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 设置工作目录
WORKDIR /app

# 1. 安装系统依赖
# ffmpeg 是 yt-dlp 处理流合并的必需组件
# curl 用于健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. 安装 Python 依赖
# 直接在这里安装，或者 COPY requirements.txt 均可
RUN pip install --no-cache-dir \
    flask \
    yt-dlp \
    requests \
    psutil

# 3. 复制源代码
COPY py-ytblive.py .

# 暴露 Flask 端口
EXPOSE 51179

# 启动命令
# 注意：不需要在 Docker 中使用 --break-system-packages
ENTRYPOINT ["python", "py-ytblive.py"]
