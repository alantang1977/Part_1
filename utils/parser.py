"""解析工具模块"""
import re
from config import URL_BLACKLIST
from collections import OrderedDict  # 正确导入OrderedDict

def parse_template(template_path):
    """解析频道模板文件，返回分类-频道有序字典"""
    with open(template_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    categories = OrderedDict()  # 使用有序字典保存分类
    current_category = None
    for line in lines:
        if "#genre#" in line:
            current_category = line.split(",", 1)[0].strip()  # 提取分类名称
            categories[current_category] = []  # 初始化分类下的频道列表
        elif current_category:
            categories[current_category].append(line.strip())  # 添加频道名称
    return categories  # 返回有序字典

def parse_source_content(content, source_type):
    """统一解析入口（支持M3U/TXT格式）"""
    if source_type == "m3u":
        return _parse_m3u(content)
    elif source_type == "txt":
        return _parse_txt(content)
    return OrderedDict()  # 返回空有序字典

def _parse_m3u(content):
    """解析M3U格式（处理EXTINF标签）"""
    channels = OrderedDict()
    entries = content.split("#EXTINF:-1,")
    for entry in entries[1:]:  # 跳过第一个空条目
        name, url = _split_m3u_entry(entry)
        if name and url:
            _add_channel(channels, name, url)
    return channels

def _split_m3u_entry(entry):
    """分割M3U条目为名称和URL"""
    parts = entry.split("\n", 1)
    name = parts[0].strip()
    url = parts[1].strip() if len(parts) > 1 else ""
    return name, url

def _parse_txt(content):
    """解析TXT格式（支持#分隔的多个URL）"""
    channels = OrderedDict()
    for line in content.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        name, urls = line.split(",", 1)
        for url in urls.split("#"):  # 处理多个URL
            url = url.strip()
            if url:
                _add_channel(channels, name, url)
    return channels

def _add_channel(channels, name, url):
    """添加频道（标准化名称，去重）"""
    cleaned_name = re.sub(r'[^\w\s-]', '', name).strip().upper()
    if cleaned_name not in channels:
        channels[cleaned_name] = []
    if url not in channels[cleaned_name]:
        channels[cleaned_name].append(url)

def _is_blacklisted(url):
    """正则表达式黑名单检测"""
    return any(re.search(bl, url, re.IGNORECASE) for bl in URL_BLACKLIST)

def _has_valid_ip(url):
    """检测有效IP地址（支持IPv4/IPv6）"""
    ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    ipv6_pattern = r'\[?[0-9a-fA-F:]+\]?'
    return re.search(f"{ipv4_pattern}|{ipv6_pattern}", url) is not None
