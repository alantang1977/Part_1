import re
import requests
import logging
from collections import OrderedDict
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


def parse_template(template_file):
    """解析模板文件，提取频道分类和名称（保持顺序）"""
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
    """清洗频道名称：去除特殊字符、统一大写、修正数字格式"""
    cleaned_name = re.sub(r'[$「」-]', '', channel_name)       # 去除特殊符号
    cleaned_name = re.sub(r'\s+', '', cleaned_name)            # 去除空格
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)  # 修正数字格式
    return cleaned_name.upper()                                # 统一大写


def fetch_channels(url):
    """从URL抓取并解析频道数据（返回有序字典）"""
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
    """解析M3U格式内容（返回有序字典：分类->[(频道名, URL)]）"""
    channels = OrderedDict()
    current_category = None
    current_channel_name = None
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            # 提取分类和频道名（处理group-title）
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                current_channel_name = match.group(2).strip()
                # 清洗CCTV开头的频道名
                if current_channel_name.startswith("CCTV"):
                    current_channel_name = clean_channel_name(current_channel_name)
                # 初始化分类容器
                if current_category not in channels:
                    channels[current_category] = []
        elif line and not line.startswith("#"):
            # 关联分类、频道名和URL
            if current_category and current_channel_name:
                channels[current_category].append((current_channel_name, line.strip()))
    return channels


def parse_txt_lines(lines):
    """解析TXT格式内容（返回有序字典：分类->[(频道名, URL)]）"""
    channels = OrderedDict()
    current_category = None
    for line in lines:
        line = line.strip()
        if "#genre#" in line:
            # 提取分类（处理#genre#标记）
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
        elif current_category and "," in line:
            # 拆分频道名和URL（支持#分隔多个URL）
            channel_name, urls = line.split(",", 1)
            cleaned_name = clean_channel_name(channel_name.strip())
            for url in urls.strip().split('#'):
                if url:
                    channels[current_category].append((cleaned_name, url.strip()))
    return channels


def match_channels(template_channels, all_channels):
    """匹配模板频道与抓取到的频道（按名称精准匹配）"""
    matched_channels = OrderedDict()
    for t_category, t_channel_names in template_channels.items():
        matched_channels[t_category] = OrderedDict()
        for t_name in t_channel_names:
            matched_urls = []
            # 遍历所有来源的分类和频道
            for a_category, a_channel_list in all_channels.items():
                for a_name, a_url in a_channel_list:
                    if t_name == a_name:
                        matched_urls.append(a_url)
            if matched_urls:
                matched_channels[t_category][t_name] = matched_urls
    return matched_channels


def filter_source_urls(template_file):
    """过滤并合并多源频道数据（保持分类顺序）"""
    template_channels = parse_template(template_file)
    all_channels = OrderedDict()  # 存储所有来源的频道（分类->[(频道名, URL)]）
    
    for url in config.source_urls:
        source_channels = fetch_channels(url)
        if not source_channels:
            continue
        
        # 合并频道数据（按分类扩展）
        for category, channel_list in source_channels.items():
            if category in all_channels:
                all_channels[category].extend(channel_list)
            else:
                all_channels[category] = channel_list.copy()
    
    return match_channels(template_channels, all_channels), template_channels


def is_ipv6(url):
    """判断URL是否包含IPv6地址（格式：http://[2001:db8::1]:8080）"""
    return re.match(r'^https?://\[[0-9a-fA-F:]+\]', url, re.IGNORECASE) is not None


def check_url_response_time(url):
    """检测URL响应时间（返回毫秒，失败时返回无穷大）"""
    try:
        start_time = datetime.now()
        # 使用HEAD请求减少数据传输
        response = requests.head(url, timeout=5, allow_redirects=True)
        response.raise_for_status()
        return (url, (datetime.now() - start_time).microseconds / 1000)
    except Exception as e:
        logging.warning(f"检测 {url} 响应时间失败: {str(e)}")
        return (url, float('inf'))


def sort_by_response_time(urls):
    """按响应时间升序排序URL（多线程加速检测）"""
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_url_response_time, urls))
    # 按响应时间排序，优先选择响应快的URL
    return [url for url, _ in sorted(results, key=lambda x: x[1])]


def update_channel_urls(channels, template_channels):
    """生成最终的M3U和TXT文件（包含排序和去重）"""
    os.makedirs("output", exist_ok=True)
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    epg_headers = f'#EXTM3U x-tvg-url="{"\",\"".join(config.epg_urls)}"\n'
    
    with open("output/live.m3u", "w", encoding="utf-8") as m3u, \
         open("output/live.txt", "w", encoding="utf-8") as txt:
        
        # 写入M3U头部和EPG信息
        m3u.write(epg_headers)
        _write_announcements(m3u, txt, current_date)
        
        written_urls = set()  # 全局去重已写入的URL
        for category in template_channels:
            txt.write(f"{category},#genre#\n")  # 写入TXT分类标记
            if category not in channels:
                continue
            
            for channel_name, urls in channels[category].items():
                _process_channel(category, channel_name, urls, m3u, txt, written_urls)


def _write_announcements(m3u, txt, current_date):
    """写入系统公告（固定频道和自定义信息）"""
    for group in config.announcements:
        txt.write(f"{group['channel']},#genre#\n")
        for entry in group['entries']:
            name = entry['name'] or f"系统公告 ({current_date})"
            # 写入M3U格式
            m3u.write(f'#EXTINF:-1 tvg-id="1" tvg-name="{name}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{name}\n')
            m3u.write(f"{entry['url']}\n")
            # 写入TXT格式
            txt.write(f"{name},{entry['url']}\n")


def _process_channel(category, channel_name, urls, m3u, txt, written_urls):
    """处理单个频道的URL：去重、排序、格式化"""
    # 去重并过滤黑名单
    unique_urls = [u for u in {url for url in urls if not _is_blacklisted(url)}]
    
    if not unique_urls:
        return  # 跳过无有效URL的频道
    
    # 按响应时间排序
    sorted_urls = sort_by_response_time(unique_urls)
    
    for idx, url in enumerate(sorted_urls, 1):
        if url in written_urls:
            continue  # 避免重复写入相同URL
        
        # 生成版本后缀（IPv6带方括号，自动识别）
        version_suffix = "$IPV6" if is_ipv6(url) else "$IPV4"
        line_suffix = f"•线路{idx}" if len(sorted_urls) > 1 else ""
        
        # 处理URL中的多余参数（保留到$符号前）
        processed_url = url.split('$', 1)[0] + version_suffix + line_suffix
        
        # 写入文件
        _write_to_file(m3u, txt, category, channel_name, idx, processed_url)
        written_urls.add(url)


def _write_to_file(m3u_file, txt_file, category, name, idx, url):
    """写入单个频道的M3U和TXT格式数据"""
    logo_url = f"{config.LOGO_BASE_URL}{name}.png"
    # M3U格式（包含EPG信息和分组）
    m3u_file.write(f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}" tvg-logo="{logo_url}" group-title="{category}",{name}\n')
    m3u_file.write(f"{url}\n")
    # TXT格式（频道名,URL）
    txt_file.write(f"{name},{url}\n")


def _is_blacklisted(url):
    """检查URL是否在黑名单中（支持部分匹配）"""
    return any(bl in url for bl in config.url_blacklist)


if __name__ == "__main__":
    template_path = "demo.txt"  # 模板文件路径
    matched_channels, template = filter_source_urls(template_path)
    update_channel_urls(matched_channels, template)
    logging.info("频道列表更新完成，已生成标准M3U和TXT文件")
