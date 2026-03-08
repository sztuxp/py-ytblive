# 使用官方轻量级 Python 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖 (yt-dlp 的运行通常依赖 ffmpeg)
# 同时清理缓存以减小镜像体积
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制你的应用脚本
COPY py-ytblive.py .

# 暴露 Flask 默认端口（如果你的代码里改了端口，这里也要对应修改）
EXPOSE 51179

# 启动脚本
# 使用 -u 参数确保日志能实时输出到 Docker 控制台
ENTRYPOINT ["python", "-u", "py-ytblive.py"]
