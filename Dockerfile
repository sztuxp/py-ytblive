FROM python:3.11-slim

WORKDIR /app

# 安装 ffmpeg (yt-dlp 必需)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY py-ytblive.py .

# 暴露源代码中的端口
EXPOSE 51179

# 运行命令。注意使用 -u 确保日志实时输出
CMD ["python", "-u", "py-ytblive.py"]
