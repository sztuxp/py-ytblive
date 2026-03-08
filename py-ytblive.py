#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YouTube 直播流代理服务器 (Docker 优化版)
功能：支持 PotPlayer 等播放器通过 HTTP 接口播放 YouTube 直播，支持自动缓存刷新。
"""

from flask import Flask, Response, request, jsonify, redirect as flask_redirect
import yt_dlp
import requests
import logging
import os
import sys
import threading
import time

# ============================================
# 配置区域 - 根据需要修改
# ============================================

# 需要自动缓存的频道列表
AUTO_CACHE_CHANNELS = [
    '@ABCNews',
    '@SkyNews',
    '@mirrornow',
    'TVBSNEWS01'
]

# 自动刷新与缓存设置
AUTO_REFRESH_INTERVAL = 1800   # 每 30 分钟刷新一次
CACHE_DURATION = 1800          # 流 URL 缓存 30 分钟
CHANNEL_CACHE_DURATION = 300   # 频道映射缓存 5 分钟
VIDEO_MAX_HEIGHT = 1080        # 优先 1080p

# 服务器设置
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 51179
ENABLE_AUTO_REFRESH = True

# Cookie 文件路径 (建议通过 Docker -v 挂载到 /app/cookies.txt)
COOKIE_FILE = 'cookies.txt'

# ============================================
# 系统初始化
# ============================================

app = Flask(__name__)

# 日志配置：输出到 Stdout 以便 Docker 捕获
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 双层缓存系统
url_cache = {}      # 视频 ID -> 流 URL
channel_cache = {}  # 频道名 -> 视频 ID

# ============================================
# 核心逻辑
# ============================================

def get_common_ydl_opts(is_flat=False):
    """构造 yt-dlp 通用配置，自动检测 Cookie"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        # 自动检测 Cookie 文件
        'cookiefile': COOKIE_FILE if os.path.exists(COOKIE_FILE) else None,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    if is_flat:
        opts['extract_flat'] = True
    else:
        # 设置清晰度过滤
        opts['format'] = f'bestvideo[height<={VIDEO_MAX_HEIGHT}][ext=mp4]+bestaudio[ext=m4a]/best[height<={VIDEO_MAX_HEIGHT}]/best'
    
    return opts

def get_channel_live_video_id(channel_handle):
    """获取频道当前直播的视频 ID (带缓存)"""
    channel_key = channel_handle
    if not channel_key.startswith('@') and not channel_key.startswith('http'):
        channel_key = f"@{channel_key}"
    
    # 检查缓存
    if channel_key in channel_cache:
        entry = channel_cache[channel_key]
        if time.time() - entry['timestamp'] < CHANNEL_CACHE_DURATION:
            return entry['video_id']
    
    # 构建 URL
    if channel_handle.startswith('http'):
        url = channel_handle
    else:
        handle = channel_handle if channel_handle.startswith('@') else f"@{channel_handle}"
        url = f"https://www.youtube.com/{handle}/live"
    
    try:
        logger.info(f"正在解析频道直播 ID: {url}")
        with yt_dlp.YoutubeDL(get_common_ydl_opts(is_flat=True)) as ydl:
            info = ydl.extract_info(url, download=False)
            video_id = info.get('id')
            if not video_id:
                raise Exception("该频道当前未在直播")
            
            channel_cache[channel_key] = {'video_id': video_id, 'timestamp': time.time()}
            return video_id
    except Exception as e:
        logger.error(f"解析频道失败: {str(e)}")
        raise

def get_youtube_stream_url(video_id):
    """获取 YouTube 真实流 URL (带缓存)"""
    if video_id in url_cache:
        entry = url_cache[video_id]
        if time.time() - entry['timestamp'] < CACHE_DURATION:
            return entry['url']
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        logger.info(f"正在获取视频流 URL: {video_id}")
        with yt_dlp.YoutubeDL(get_common_ydl_opts(is_flat=False)) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url')
            
            url_cache[video_id] = {
                'url': stream_url,
                'timestamp': time.time(),
                'resolution': f"{info.get('width')}x{info.get('height')}"
            }
            return stream_url
    except Exception as e:
        logger.error(f"获取视频流失败: {str(e)}")
        raise

# ============================================
# 自动刷新线程
# ============================================

def refresh_all_channels():
    if not AUTO_CACHE_CHANNELS: return
    logger.info(f"[自动刷新] 开始刷新 {len(AUTO_CACHE_CHANNELS)} 个配置频道...")
    for channel in AUTO_CACHE_CHANNELS:
        try:
            vid = get_channel_live_video_id(channel)
            get_youtube_stream_url(vid)
            logger.info(f"[自动刷新] 成功: {channel}")
        except:
            logger.warning(f"[自动刷新] 失败: {channel}")
        time.sleep(2)

def auto_refresh_loop():
    time.sleep(10) # 启动后延迟执行
    while True:
        refresh_all_channels()
        time.sleep(AUTO_REFRESH_INTERVAL)

def stream_generator(url):
    """流代理模式下的数据转发"""
    try:
        with requests.get(url, stream=True, timeout=15) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                if chunk: yield chunk
    except Exception as e:
        logger.error(f"代理传输中断: {str(e)}")

# ============================================
# Flask 路由
# ============================================

@app.route('/')
def index():
    return f"<h1>YouTube Live Proxy</h1><p>端口: {SERVER_PORT}</p><p>已缓存视频: {len(url_cache)}</p>"

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'cookies_detected': os.path.exists(COOKIE_FILE)}), 200

@app.route('/<path:channel_path>')
def fast_proxy(channel_path):
    """最常用的路径：直接 302 重定向到流 URL"""
    try:
        vid = get_channel_live_video_id(channel_path)
        stream_url = get_youtube_stream_url(vid)
        return flask_redirect(stream_url, code=302)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/video')
def video_proxy():
    """支持参数化的视频请求"""
    channel = request.args.get('channel')
    video_id = request.args.get('id')
    redirect_mode = request.args.get('redirect', 'true').lower() == 'true'

    try:
        if channel:
            video_id = get_channel_live_video_id(channel)
        
        if not video_id:
            return jsonify({'error': 'Missing ID or Channel'}), 400
        
        stream_url = get_youtube_stream_url(video_id)

        if redirect_mode:
            return flask_redirect(stream_url, code=302)
        else:
            return Response(stream_generator(stream_url), mimetype='video/mp4')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/cache/status')
def cache_status():
    return jsonify({
        'url_cache_size': len(url_cache),
        'channel_cache_size': len(channel_cache),
        'cookies_active': os.path.exists(COOKIE_FILE)
    })

# ============================================
# 程序入口
# ============================================

if __name__ == '__main__':
    logger.info("="*50)
    logger.info("YouTube 直播代理服务启动 (Docker 模式)")
    if os.path.exists(COOKIE_FILE):
        logger.info(f"检测到 Cookie 文件: {COOKIE_FILE}, 已启用身份认证。")
    else:
        logger.warning("未检测到 cookies.txt, 可能会遇到人机验证(403)错误。")
    logger.info("="*50)

    # 启动异步刷新线程
    if ENABLE_AUTO_REFRESH:
        threading.Thread(target=auto_refresh_loop, daemon=True).start()

    # 启动 Flask。注意：不使用 debug 模式以防在 Docker 中产生双倍进程
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, threaded=True)
