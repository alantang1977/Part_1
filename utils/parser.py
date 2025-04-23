"""解析工具模块"""
import re
from collections import OrderedDict  # 用于保持分类/频道顺序
from config import url_blacklist     # 修正变量名（小写）

def parse_template(template_path):
    """解析频道模板文件，生成分类-频道列表（有序字典）"""
    template_channels = OrderedDict()
    current_category = None
    
    with open(template_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "#genre#" in line:
                current_category = line.split(",", 1)[0].strip()
                template_channels[current_category] = []
            elif current_category:
                template_channels[current_category].append(line.strip())
    
    return template_channels

def parse_source_content(content, source_type):
    """解析数据源内容（M3U/TXT），返回有序字典"""
    channels = OrderedDict()  # 保持分类顺序
    
    if source_type == "m3u":
        _parse_m3u(content, channels)
    elif source_type == "txt":
        _parse_txt(content, channels)
    
    return channels

def _parse_m3u(content, channels):
    """解析M3U格式内容（内部方法）"""
    entries = content.split("#EXTINF:-1,")
    for entry in entries[1:]:  # 跳过第一个空元素
        parts = entry.split("\n", 1)
        if len(parts) < 2:
            continue  # 跳过不完整的条目
        
        channel_name = parts[0].strip()
        url = parts[1].strip()
        
        if _is_valid_entry(channel_name, url):
            _add_channel(channels, channel_name, url)

def _parse_txt(content, channels):
    """解析TXT格式内容（内部方法，每行格式：频道名,URL）"""
    for line in content.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        
        name, url = line.split(",", 1)
        name = name.strip()
        url = url.strip()
        
        if _is_valid_entry(name, url):
            _add_channel(channels, name, url)

def _is_valid_entry(name, url):
    """验证条目有效性：非空、不在黑名单、包含有效IP"""
    if not name or not url:
        return False
    if _is_blacklisted(url):
        return False
    if not _has_valid_ip(url):
        return False
    return True

def _add_channel(channels, name, url):
    """统一添加频道（自动去重，保持顺序）"""
    if name not in channels:
        channels[name] = []
    if url not in channels[name]:  # 避免重复添加相同URL
        channels[name].append(url)

def _is_blacklisted(url):
    """检查URL是否在黑名单中（支持部分匹配）"""
    return any(bl in url for bl in url_blacklist)

def _has_valid_ip(url):
    """检查URL是否包含有效IPv4或IPv6地址"""
    ipv4_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"       # IPv4地址
    ipv6_pattern = r"\[([0-9a-fA-F:]+)\]"               # IPv6地址（带方括号）
    return re.search(f"{ipv4_pattern}|{ipv6_pattern}", url, re.IGNORECASE) is not None
