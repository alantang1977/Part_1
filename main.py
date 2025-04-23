import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
import os
from concurrent.futures import ThreadPoolExecutor
from utils.parser import parse_template as parse_template_utils, parse_source_content

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("function.log", "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def fetch_channels(url):
    """从URL抓取频道列表并解析"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        content = response.text
        is_m3u = any(line.startswith("#EXTINF") for line in content.split("\n")[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"成功获取 {url}，判断为 {source_type} 格式")
        return parse_source_content(content, source_type)
    except requests.RequestException as e:
        logging.error(f"获取 {url} 失败: {str(e)}")
        return {}

def filter_source_urls(template_file):
    """过滤并合并源URL的频道信息"""
    template_channels = parse_template_utils(template_file)
    all_channels = OrderedDict()
    for url in config.source_urls:
        merged_channels = fetch_channels(url)
        for category, channels in merged_channels.items():
            if category not in all_channels:
                all_channels[category] = OrderedDict()
            for name, urls in channels.items():
                all_channels[category][name] = all_channels[category].get(name, []) + urls
    return match_channels(template_channels, all_channels), template_channels

def match_channels(template_channels, all_channels):
    """匹配模板频道与抓取到的频道"""
    matched = OrderedDict()
    for t_category, t_names in template_channels.items():
        matched[t_category] = OrderedDict()
        for t_name in t_names:
            for a_category, a_channels in all_channels.items():
                if t_name in a_channels:
                    matched[t_category][t_name] = a_channels[t_name]
    return matched

def is_ipv6(url):
    """判断URL是否包含IPv6地址"""
    return re.match(r'^https?://\[[0-9a-fA-F:]+\]', url, re.IGNORECASE) is not None

def check_url_response_time(url):
    """检测URL响应时间（毫秒）"""
    try:
        start_time = datetime.now()
        response = requests.head(url, timeout=5, allow_redirects=True)
        response.raise_for_status()
        return (url, (datetime.now() - start_time).microseconds / 1000)
    except Exception:
        return (url, float('inf'))

def sort_by_response_time(urls):
    """根据响应时间排序URL（升序）"""
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_url_response_time, urls))
    return [url for url, _ in sorted(results, key=lambda x: x[1])]

def update_channel_urls(channels, template_channels):
    """更新频道URL到文件（统一M3U和TXT格式）"""
    os.makedirs("output", exist_ok=True)
    current_date = datetime.now().strftime("%Y-%m-%d")
    epg_quoted = [f'"{url}"' for url in config.epg_urls]
    
    with open("output/live.m3u", "w", encoding="utf-8") as m3u, \
         open("output/live.txt", "w", encoding="utf-8") as txt:

        m3u.write(f'#EXTM3U x-tvg-url={",".join(epg_quoted)}\n')
        _write_announcements(m3u, txt, current_date)
        _write_channels(channels, template_channels, m3u, txt)

def _write_announcements(m3u, txt, current_date):
    """写入系统公告"""
    for group in config.announcements:
        txt.write(f"{group['channel']},#genre#\n")
        for entry in group['entries']:
            name = entry['name'] or current_date
            m3u.write(f'#EXTINF:-1 tvg-id="1" tvg-name="{name}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{name}\n')
            m3u.write(f"{entry['url']}\n")
            txt.write(f"{name},{entry['url']}\n")

def _write_channels(channels, template_channels, m3u, txt):
    """写入频道内容（统一处理所有URL）"""
    written_urls = set()
    for category, names in template_channels.items():
        txt.write(f"{category},#genre#\n")
        if category in channels:
            for name in names:
                if name in channels[category]:
                    _process_channel(category, name, channels[category][name], m3u, txt, written_urls)

def _process_channel(category, name, urls, m3u, txt, written_urls):
    """处理单个频道的URL排序和写入"""
    unique_urls = [u for u in {u for u in urls if u and not _is_blacklisted(u)}]
    sorted_urls = sort_by_response_time(unique_urls)
    
    for idx, url in enumerate(sorted_urls, 1):
        if url in written_urls:
            continue
        version_suffix = "$IPV6" if is_ipv6(url) else "$IPV4"
        line_suffix = f"•线路{idx}" if len(sorted_urls) > 1 else ""
        processed_url = f"{url.split('$', 1)[0]}{version_suffix}{line_suffix}"
        _write_to_file(m3u, txt, category, name, idx, processed_url)
        written_urls.add(url)

def _write_to_file(m3u_file, txt_file, category, name, idx, url):
    """写入单个频道到文件"""
    logo = f"{config.LOGO_BASE_URL}{name}.png"
    m3u_file.write(f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}\n')
    m3u_file.write(f"{url}\n")
    txt_file.write(f"{name},{url}\n")

def _is_blacklisted(url):
    """检查URL是否在黑名单中"""
    return any(bl in url for bl in config.url_blacklist)

if __name__ == "__main__":
    template = "demo.txt"
    matched, tmpl = filter_source_urls(template)
    update_channel_urls(matched, tmpl)
    logging.info("频道列表更新完成，已生成标准M3U和TXT文件")
