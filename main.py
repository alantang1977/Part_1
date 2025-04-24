import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("function.log", "a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def parse_template(template_file):
    """解析模板文件，提取频道分类和名称"""
    template_channels = OrderedDict()
    current_category = None
    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    channel_name = line.strip()
                    template_channels[current_category].append(channel_name)
    return template_channels

def clean_channel_name(channel_name):
    """清洗频道名称（去除特殊字符并统一大写）"""
    cleaned_name = re.sub(r'[$「」-]', '', channel_name)
    cleaned_name = re.sub(r'\s+', '', cleaned_name)
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)
    return cleaned_name.upper()

def fetch_channels(url):
    """从URL抓取频道列表并解析"""
    channels = OrderedDict()
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        lines = response.text.split("\n")
        is_m3u = any(line.startswith("#EXTINF") for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"成功获取 {url}，判断为 {source_type} 格式")

        if is_m3u:
            channels = parse_m3u_lines(lines)
        else:
            channels = parse_txt_lines(lines)

        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"{url} 包含频道分类: {categories}")
    except requests.RequestException as e:
        logging.error(f"获取 {url} 失败: {str(e)}")
    return channels

def parse_m3u_lines(lines):
    """解析M3U格式内容（提取分类和频道名）"""
    channels = OrderedDict()
    current_category = None
    current_channel_name = None
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            # 提取分类和频道名
            group_title = re.search(r'group-title="(.*?)"', line).group(1) if re.search(r'group-title="(.*?)"', line) else "未分类"
            channel_name = re.split(r'group-title=".*?",', line)[1].strip()
            channel_name = clean_channel_name(channel_name)
            current_category = group_title
            if current_category not in channels:
                channels[current_category] = []
            current_channel_name = channel_name
        elif line and not line.startswith("#"):
            if current_category and current_channel_name:
                channels[current_category].append((current_channel_name, line.strip()))
    return channels

def parse_txt_lines(lines):
    """解析TXT格式内容（每行频道名,URL）"""
    channels = OrderedDict()
    current_category = None
    for line in lines:
        line = line.strip()
        if "#genre#" in line:
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
        elif current_category and "," in line:
            channel_name, urls = line.split(",", 1)
            channel_name = clean_channel_name(channel_name.strip())
            for url in urls.strip().split('#'):
                if url:
                    channels[current_category].append((channel_name, url.strip()))
    return channels

def match_channels(template_channels, all_channels):
    """匹配模板频道与抓取到的频道（支持模糊匹配）"""
    matched_channels = OrderedDict()
    for t_category, t_names in template_channels.items():
        matched_channels[t_category] = OrderedDict()
        for t_name in t_names:
            # 精确匹配（可扩展为模糊匹配）
            matched_urls = []
            for a_category, a_entries in all_channels.items():
                for a_name, a_url in a_entries:
                    if a_name == t_name:
                        matched_urls.append(a_url)
            if matched_urls:
                matched_channels[t_category][t_name] = matched_urls
    return matched_channels

def filter_source_urls(template_file):
    """过滤并合并源URL的频道信息（多线程抓取）"""
    template_channels = parse_template(template_file)
    all_channels = OrderedDict()
    
    # 多线程抓取所有数据源
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_channels, url) for url in config.source_urls]
        for future in as_completed(futures):
            merged = future.result()
            if merged:
                merge_channels(all_channels, merged)
    
    return match_channels(template_channels, all_channels), template_channels

def merge_channels(target, source):
    """合并两个频道字典（按分类合并）"""
    for category, entries in source.items():
        if category in target:
            target[category].extend(entries)
        else:
            target[category] = entries

def is_ipv6(url):
    """判断URL是否包含IPv6地址"""
    return re.match(r'^https?://\[[0-9a-fA-F:]+\]', url, re.IGNORECASE) is not None

def check_url_response(url):
    """检测URL响应时间（返回有效URL和响应时间，失败返回None）"""
    try:
        start_time = datetime.now()
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            latency = (datetime.now() - start_time).microseconds / 1000
            return (url, latency)
        else:
            logging.warning(f"URL {url} 状态码异常: {response.status_code}")
            return None
    except Exception as e:
        logging.warning(f"URL {url} 检测失败: {str(e)}")
        return None

def sort_urls_by_latency(urls):
    """按响应时间排序URL（升序，过滤无效URL）"""
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = list(executor.map(check_url_response, urls))
    
    valid_results = [result for result in results if result is not None]
    if not valid_results:
        return []
    
    # 按响应时间排序
    return [url for url, _ in sorted(valid_results, key=lambda x: x[1])]

def update_channel_urls(channels, template_channels):
    """更新频道URL到文件（按响应时间优先级生成M3U/TXT）"""
    os.makedirs("output", exist_ok=True)
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    epg_quoted = [f'"{url}"' for url in config.epg_urls]
    
    with open("output/live.m3u", "w", encoding="utf-8") as m3u, \
         open("output/live.txt", "w", encoding="utf-8") as txt:

        m3u.write(f'#EXTM3U x-tvg-url={",".join(epg_quoted)}\n')
        _write_announcements(m3u, txt, current_date)
        _write_priority_channels(channels, template_channels, m3u, txt)

def _write_announcements(m3u, txt, current_date):
    """写入系统公告（保留原功能）"""
    for group in config.announcements:
        txt.write(f"{group['channel']},#genre#\n")
        for entry in group['entries']:
            name = entry['name'] or f"系统公告-{current_date}"
            m3u.write(f'#EXTINF:-1 tvg-id="1" tvg-name="{name}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{name}\n')
            m3u.write(f"{entry['url']}\n")
            txt.write(f"{name},{entry['url']}\n")

def _write_priority_channels(channels, template_channels, m3u, txt):
    """按响应时间优先级写入频道（核心优化点）"""
    written_urls = set()  # 全局去重
    for category in template_channels:
        txt.write(f"{category},#genre#\n")
        if category not in channels:
            continue
        
        for channel_name in template_channels[category]:
            if channel_name not in channels[category]:
                continue
            
            urls = channels[category][channel_name]
            # 过滤黑名单并检测响应时间
            valid_urls = [url for url in urls if not _is_blacklisted(url)]
            sorted_urls = sort_urls_by_latency(valid_urls)
            
            if not sorted_urls:
                logging.warning(f"频道 {channel_name} 无有效URL，跳过")
                continue
            
            for idx, url in enumerate(sorted_urls, 1):
                if url in written_urls:
                    continue
                # 生成M3U元数据
                logo = f"{config.LOGO_BASE_URL}{channel_name}.png"
                m3u.write(f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{channel_name}" tvg-logo="{logo}" group-title="{category}",{channel_name} (线路{idx})\n')
                m3u.write(f"{url}\n")
                txt.write(f"{channel_name},{url}\n")
                written_urls.add(url)

def _is_blacklisted(url):
    """检查URL是否在黑名单中（优化匹配逻辑）"""
    return any(bl in url for bl in config.url_blacklist)

if __name__ == "__main__":
    template = "demo.txt"
    matched, tmpl = filter_source_urls(template)
    update_channel_urls(matched, tmpl)
    logging.info("频道列表更新完成，已按响应时间优先级生成文件")
