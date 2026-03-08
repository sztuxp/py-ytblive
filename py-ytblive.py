#!/usr/bin/env python3
from flask import Flask, Response, request, jsonify, redirect as flask_redirect
import yt_dlp
import requests
import logging
import os
import sys
import threading
import time

# ============================================
# 配置区域
# ============================================
AUTO_CACHE_CHANNELS = ['@ABCNews', '@SkyNews', '@mirrornow', 'TVBSNEWS01']
AUTO_REFRESH_INTERVAL = 1800  
CACHE_DURATION = 1800  
CHANNEL_CACHE_DURATION = 300  
VIDEO_MAX_HEIGHT = 1080  
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 51179
ENABLE_AUTO_REFRESH = True

# ============================================
# 系统初始化
# ============================================
app = Flask(__name__)

# 修改日志配置：输出到终端(stdout)，方便 Docker 查看
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

url_cache = {}
channel_cache = {}

# 获取 ID 和 URL 的函数保持不变 ...
def get_channel_live_video_id(channel_handle):
    channel_key = channel_handle
    if not channel_key.startswith('@') and not channel_key.startswith('http'):
        channel_key = f"@{channel_key}"
    
    if channel_key in channel_cache:
        cache_entry = channel_cache[channel_key]
        if time.time() - cache_entry['timestamp'] < CHANNEL_CACHE_DURATION:
            return cache_entry['video_id']

    if channel_handle.startswith('http'): channel_url = channel_handle
    elif channel_handle.startswith('@'): channel_url = f"https://www.youtube.com/{channel_handle}/live"
    else: channel_url = f"https://www.youtube.com/@{channel_handle}/live"
    
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
            video_id = info.get('id')
            if not video_id: raise Exception("没有直播")
            channel_cache[channel_key] = {'video_id': video_id, 'timestamp': time.time()}
            return video_id
    except Exception as e:
        logger.error(f"获取频道直播失败: {str(e)}")
        raise

def get_youtube_stream_url(video_id):
    if video_id in url_cache:
        entry = url_cache[video_id]
        if time.time() - entry['timestamp'] < CACHE_DURATION:
            return entry['url']

    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'format': f'bestvideo[height<={VIDEO_MAX_HEIGHT}][ext=mp4]+bestaudio[ext=m4a]/best',
        'quiet': True, 'no_warnings': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            stream_url = info.get('url')
            url_cache[video_id] = {'url': stream_url, 'timestamp': time.time()}
            return stream_url
    except Exception as e:
        logger.error(f"获取流失败: {str(e)}")
        raise

# 自动刷新逻辑保持不变 ...
def refresh_all_channels():
    for channel in AUTO_CACHE_CHANNELS:
        try:
            vid = get_channel_live_video_id(channel)
            get_youtube_stream_url(vid)
            logger.info(f"自动刷新成功: {channel}")
        except: pass
        time.sleep(2)

def auto_refresh_loop():
    time.sleep(10)
    while True:
        refresh_all_channels()
        time.sleep(AUTO_REFRESH_INTERVAL)

# 路由部分保持不变 ...
@app.route('/<path:channel_path>')
def channel_proxy(channel_path):
    try:
        vid = get_channel_live_video_id(channel_path)
        url = get_youtube_stream_url(vid)
        return flask_redirect(url, code=302)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health(): return jsonify({'status': 'ok'})

# ============================================
# 入口点：修改了这里！
# ============================================
if __name__ == '__main__':
    logger.info("YouTube直播代理正在启动 (Docker 模式)...")
    
    # 启动自动刷新线程
    if ENABLE_AUTO_REFRESH and AUTO_CACHE_CHANNELS:
        t = threading.Thread(target=auto_refresh_loop, daemon=True)
        t.start()
    
    # 直接在前台运行 Flask，不要调用 daemonize()
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True)
