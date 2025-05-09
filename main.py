import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple
import config
from utils.parser import parse_template, parse_source_content

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("function.log", "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def clean_channel_name(channel_name: str) -> str:
    """清洗频道名称（去除特殊字符并统一大写）"""
    cleaned_name = re.sub(r'[$「」-]', '', channel_name)
    cleaned_name = re.sub(r'\s+', '', cleaned_name)
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)
    return cleaned_name.upper()

def fetch_channels(url: str) -> OrderedDict[str, List[Tuple[str, str]]]:
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

def parse_m3u_lines(lines: List[str]) -> OrderedDict[str, List[Tuple[str, str]]]:
    """解析M3U格式内容（增强错误处理）"""
    channels = OrderedDict()
    current_category = None
    current_channel_name = None
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            # 支持带group-title和不带group-title的两种格式
            match = re.search(r'group-title="(.*?)"[,]?(.*)|,([^,]+)', line)
            if match:
                # 提取分类和频道名称
                group_title = match.group(1) or "未分类"  # 有group-title时使用，否则默认"未分类"
                channel_name_part = match.group(2) or match.group(3)  # 处理两种格式的频道名称
                current_channel_name = clean_channel_name(channel_name_part.strip())
                current_category = group_title.strip()
                
                if current_category not in channels:
                    channels[current_category] = []
            else:
                logging.warning(f"无效的M3U格式行，跳过: {line}")
                continue  # 匹配失败时跳过当前行
        elif line and not line.startswith("#"):
            if current_category and current_channel_name:
                channels[current_category].append((current_channel_name, line.strip()))
    return channels

def parse_txt_lines(lines: List[str]) -> OrderedDict[str, List[Tuple[str, str]]]:
    """解析TXT格式内容（每行频道名,URL）"""
    channels = OrderedDict()
    current_category = None
    for line in lines:
        line = line.strip()
        if "#genre#" in line:
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
        elif current_category and "," in line:
            try:
                channel_name, url = line.split(",", 1)
                cleaned_name = clean_channel_name(channel_name.strip())
                for u in url.strip().split('#'):
                    if u:
                        channels[current_category].append((cleaned_name, u.strip()))
            except ValueError:
                logging.warning(f"无效的TXT格式行，跳过: {line}")
                continue
    return channels

def match_channels(template_channels: OrderedDict[str, List[str]], all_channels: OrderedDict[str, List[Tuple[str, str]]]) -> OrderedDict[str, OrderedDict[str, List[str]]]:
    """匹配模板频道与抓取到的频道"""
    matched_channels = OrderedDict()
    for t_category, t_channels in template_channels.items():
        matched_channels[t_category] = OrderedDict()
        for t_name in t_channels:
            for a_category, a_channel_list in all_channels.items():
                for a_name, a_url in a_channel_list:
                    if t_name.upper() == a_name:  # 模板名称统一大写匹配
                        matched_channels[t_category].setdefault(t_name, []).append(a_url)
    return matched_channels

def filter_source_urls(template_file: str) -> Tuple[OrderedDict[str, OrderedDict[str, List[str]]], OrderedDict[str, List[str]]]:
    """过滤并合并源URL的频道信息"""
    template_channels = parse_template(template_file)
    all_channels = OrderedDict()
    for url in config.source_urls:
        merged_channels = fetch_channels(url)
        merge_channels(all_channels, merged_channels)
    return match_channels(template_channels, all_channels), template_channels

def merge_channels(target: OrderedDict[str, List[Tuple[str, str]]], source: OrderedDict[str, List[Tuple[str, str]]]) -> None:
    """合并两个频道字典"""
    for category, channel_list in source.items():
        if category in target:
            target[category].extend(channel_list)
        else:
            target[category] = channel_list

def is_ipv6(url: str) -> bool:
    """判断URL是否包含IPv6地址"""
    return re.match(r'^https?://\[[0-9a-fA-F:]+\]', url, re.IGNORECASE) is not None

def check_url_response_time(url: str) -> Tuple[str, float]:
    """检测URL响应时间（毫秒）"""
    try:
        start_time = datetime.now()
        response = requests.head(url, timeout=5, allow_redirects=True)
        response.raise_for_status()
        return (url, (datetime.now() - start_time).microseconds / 1000)
    except Exception as e:
        logging.warning(f"URL {url} 响应检测失败: {str(e)}")
        return (url, float('inf'))

def sort_by_response_time(urls: List[str]) -> List[str]:
    """根据响应时间排序URL（升序）"""
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_url_response_time, urls))
    return [url for url, _ in sorted(results, key=lambda x: x[1])]

def update_channel_urls(channels: OrderedDict[str, OrderedDict[str, List[str]]], template_channels: OrderedDict[str, List[str]]) -> None:
    """更新频道URL到文件（统一M3U和TXT格式）"""
    os.makedirs("output", exist_ok=True)  # 创建输出目录
    current_date = datetime.now().strftime("%Y-%m-%d")
    epg_quoted = [f'"{url}"' for url in config.epg_urls]
    
    with open("output/live.m3u", "w", encoding="utf-8") as m3u, \
         open("output/live.txt", "w", encoding="utf-8") as txt:

        m3u.write(f'#EXTM3U x-tvg-url={",".join(epg_quoted)}\n')
        _write_announcements(m3u, txt, current_date)
        _write_channels(channels, template_channels, m3u, txt)

def _write_announcements(m3u: "TextIOWrapper", txt: "TextIOWrapper", current_date: str) -> None:
    """写入系统公告"""
    for group in config.announcements:
        txt.write(f"{group['channel']},#genre#\n")
        for entry in group['entries']:
            name = entry['name'] or current_date
            m3u.write(f'#EXTINF:-1 tvg-id="1" tvg-name="{name}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{name}\n')
            m3u.write(f"{entry['url']}\n")
            txt.write(f"{name},{entry['url']}\n")

def _write_channels(channels: OrderedDict[str, OrderedDict[str, List[str]]], template_channels: OrderedDict[str, List[str]], m3u: "TextIOWrapper", txt: "TextIOWrapper") -> None:
    """写入频道内容（统一处理所有URL）"""
    written_urls = set()  # 统一管理已写入的URL
    for category, channel_list in template_channels.items():
        txt.write(f"{category},#genre#\n")
        if category in channels:
            for channel_name in channel_list:
                if channel_name in channels[category]:
                    _process_channel(
                        category,
                        channel_name,
                        channels[category][channel_name],
                        m3u, txt,
                        written_urls
                    )

def _process_channel(category: str, channel_name: str, urls: List[str], m3u: "TextIOWrapper", txt: "TextIOWrapper", written_urls: set) -> None:
    """处理单个频道的URL排序和写入"""
    # 去重并过滤黑名单
    unique_urls = [u for u in {u for u in urls if u and not _is_blacklisted(u)}]
    
    # 按响应时间排序
    sorted_urls = sort_by_response_time(unique_urls)
    
    # 生成带序号的URL
    for idx, url in enumerate(sorted_urls, 1):
        if url in written_urls:
            continue
        version_suffix = "$IPV6" if is_ipv6(url) else "$IPV4"
        line_suffix = f"•线路{idx}" if len(sorted_urls) > 1 else ""
        processed_url = f"{url.split('$', 1)[0]}{version_suffix}{line_suffix}"
        
        _write_to_file(m3u, txt, category, channel_name, idx, processed_url)
        written_urls.add(url)

def _write_to_file(m3u_file: "TextIOWrapper", txt_file: "TextIOWrapper", category: str, name: str, idx: int, url: str) -> None:
    """写入单个频道到文件"""
    logo = f"{config.LOGO_BASE_URL}{name}.png"
    m3u_file.write(f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}\n')
    m3u_file.write(f"{url}\n")
    txt_file.write(f"{name},{url}\n")

def _is_blacklisted(url: str) -> bool:
    """检查URL是否在黑名单中"""
    return any(bl in url for bl in config.url_blacklist)

if __name__ == "__main__":
    template = "demo.txt"
    matched, tmpl = filter_source_urls(template)
    update_channel_urls(matched, tmpl)
    logging.info("频道列表更新完成，已生成标准M3U和TXT文件")
