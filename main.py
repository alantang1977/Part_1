import re
import requests
import logging
from datetime import datetime
import config
import os
from concurrent.futures import ThreadPoolExecutor

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("function.log", "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# 全局URL响应时间缓存
url_response_cache = {}

def clean_channel_name(name: str) -> str:
    """标准化频道名称（去除特殊字符并转大写）"""
    return re.sub(r'[^\w\s-]', '', name).strip().upper()

def parse_template(template_file):
    """解析模板文件，提取频道分类和名称"""
    template_channels = {}
    current_category = None
    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    template_channels[current_category].append(line.strip())
    return template_channels

def fetch_channels(url):
    """从URL抓取频道列表并解析"""
    channels = {}
    try:
        response = requests.get(url, timeout=10, stream=True)
        response.raise_for_status()
        lines = response.iter_lines(decode_unicode=True)
        is_m3u = any(line.startswith("#EXTINF") for line in lines)
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"成功获取 {url}，判断为 {source_type} 格式")

        if is_m3u:
            channels = parse_m3u_lines(lines)
        else:
            channels = parse_txt_lines(lines)

        if channels:
            logging.info(f"{url} 包含频道分类: {', '.join(channels.keys())}")
    except requests.RequestException as e:
        logging.error(f"获取 {url} 失败: {str(e)}")
    return channels

def parse_m3u_lines(lines):
    """解析M3U格式内容"""
    channels = {}
    current_category = None
    current_channel_name = None
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                current_channel_name = clean_channel_name(match.group(2).strip())  # 修正此处函数引用
                if current_category not in channels:
                    channels[current_category] = []
        elif line and not line.startswith("#"):
            if current_category and current_channel_name:
                channels[current_category].append((current_channel_name, line))
    return channels

# 以下代码保持不变...
