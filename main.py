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

def parse_template(template_file):
    """解析模板文件，提取频道分类和名称（优化：使用普通字典）"""
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
    """从URL抓取频道列表并解析（优化：简化格式判断）"""
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
    """解析M3U格式内容（优化：流式处理）"""
    channels = {}
    current_category = None
    current_channel_name = None
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                current_channel_name = clean_channel_name(match.group(2).strip())
                if current_category not in channels:
                    channels[current_category] = []
        elif line and not line.startswith("#"):
            if current_category and current_channel_name:
                channels[current_category].append((current_channel_name, line))
    return channels

def parse_txt_lines(lines):
    """解析TXT格式内容（优化：流式处理）"""
    channels = {}
    current_category = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "#genre#" in line:
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
        elif current_category and "," in line:
            name, url = line.split(",", 1)
            cleaned_name = clean_channel_name(name.strip())
            channels[current_category].extend([(cleaned_name, u.strip()) for u in url.split('#') if u])
    return channels

def filter_source_urls(template_file):
    """过滤并合并源URL的频道信息（优化：提前收集所有URL）"""
    template_channels = parse_template(template_file)
    all_channels = {}
    global_urls = set()
    
    # 第一阶段：收集所有唯一URL
    for url in config.source_urls:
        source_channels = fetch_channels(url)
        for cat, items in source_channels.items():
            all_channels.setdefault(cat, []).extend(items)
            global_urls.update([u for _, u in items])
    
    # 第二阶段：匹配模板频道（使用集合加速查找）
    matched_channels = {cat: {} for cat in template_channels}
    for cat, items in all_channels.items():
        if cat not in matched_channels:
            continue
        for name, url in items:
            if name in template_channels.get(cat, []):
                matched_channels[cat].setdefault(name, set()).add(url)
    
    # 转换为列表并去重
    for cat in matched_channels:
        matched_channels[cat] = {k: list(v) for k, v in matched_channels[cat].items()}
    
    return matched_channels, template_channels

def check_url_response_time(url):
    """检测URL响应时间（优化：支持缓存）"""
    if url in url_response_cache:
        return (url, url_response_cache[url])
    
    try:
        start_time = datetime.now()
        response = requests.head(url, timeout=5, allow_redirects=True)
        response.raise_for_status()
        time_ms = (datetime.now() - start_time).microseconds / 1000
        url_response_cache[url] = time_ms
        return (url, time_ms)
    except Exception as e:
        url_response_cache[url] = float('inf')
        return (url, float('inf'))

def sort_all_urls(urls):
    """批量排序所有URL（优化：全局排序一次）"""
    with ThreadPoolExecutor(max_workers=20) as executor:  # 增加并发数
        results = list(executor.map(check_url_response_time, urls))
    return {url: time for url, time in sorted(results, key=lambda x: x[1])}

def update_channel_urls(channels, template_channels):
    """更新频道URL到文件（核心优化：全局处理流程）"""
    os.makedirs("output", exist_ok=True)
    current_date = datetime.now().strftime("%Y-%m-%d")
    epg_quoted = [f'"{url}"' for url in config.epg_urls]
    
    # 收集所有待处理URL
    all_urls = set()
    for cat in channels:
        for name in channels[cat]:
            all_urls.update(channels[cat][name])
    
    # 全局排序URL
    sorted_urls = sort_all_urls(all_urls)
    
    with open("output/live.m3u", "w", encoding="utf-8") as m3u, \
         open("output/live.txt", "w", encoding="utf-8") as txt:

        m3u.write(f'#EXTM3U x-tvg-url={",".join(epg_quoted)}\n')
        _write_announcements(m3u, txt, current_date)
        _write_channels(channels, template_channels, m3u, txt, sorted_urls)

def _write_channels(channels, template_channels, m3u, txt, sorted_urls):
    """写入频道内容（优化：使用预排序的URL映射）"""
    written_urls = set()
    
    for category, channel_dict in template_channels.items():
        txt.write(f"{category},#genre#\n")
        if category not in channels:
            continue
        
        for channel_name in channel_dict:
            if channel_name not in channels[category]:
                continue
            
            urls = channels[category][channel_name]
            unique_urls = [u for u in urls if u and not _is_blacklisted(u)]
            
            # 使用全局排序结果
            filtered_urls = [url for url in unique_urls if url in sorted_urls]
            sorted_by_time = sorted(filtered_urls, key=lambda x: sorted_urls[x])
            
            for idx, url in enumerate(sorted_by_time, 1):
                if url in written_urls:
                    continue
                processed_url = _process_url(url, idx, len(sorted_by_time))
                _write_to_file(m3u, txt, category, channel_name, idx, processed_url)
                written_urls.add(url)

def _process_url(url, idx, total):
    """处理URL后缀（优化：简化字符串操作）"""
    version_suffix = "$IPV6" if is_ipv6(url) else "$IPV4"
    line_suffix = f"•线路{idx}" if total > 1 else ""
    return f"{url.split('$', 1)[0]}{version_suffix}{line_suffix}"

def _write_to_file(m3u_file, txt_file, category, name, idx, url):
    """写入单个频道到文件（优化：预生成字符串）"""
    logo = f"{config.LOGO_BASE_URL}{name}.png"
    m3u_line = f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}\n{url}\n'
    txt_line = f"{name},{url}\n"
    m3u_file.write(m3u_line)
    txt_file.write(txt_line)

def _is_blacklisted(url):
    """检查URL是否在黑名单中（优化：集合快速查找）"""
    return any(bl in url for bl in config.url_blacklist)

def is_ipv6(url):
    """判断URL是否包含IPv6地址（优化：预编译正则）"""
    ipv6_re = re.compile(r'^https?://\[[0-9a-fA-F:]+\]')
    return ipv6_re.match(url) is not None

if __name__ == "__main__":
    template = "demo.txt"
    matched, tmpl = filter_source_urls(template)
    update_channel_urls(matched, tmpl)
    logging.info("频道列表更新完成，已生成标准M3U和TXT文件")
