"""解析工具模块"""
import re
from config import url_blacklist as URL_BLACKLIST

def parse_template(template_path):
    """解析频道模板，生成分类-频道列表"""
    with open(template_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    categories = OrderedDict()
    current_category = None
    for line in lines:
        if "#genre#" in line:
            current_category = line.split(",")[0].strip()
            categories[current_category] = []
        elif current_category:
            categories[current_category].append(line.strip())
    return categories

def parse_source_content(content, source_type):
    """解析数据源内容（M3U/TXT）"""
    channels = OrderedDict()
    if source_type == "m3u":
        return _parse_m3u(content, channels)
    elif source_type == "txt":
        return _parse_txt(content, channels)
    return channels

def _parse_m3u(content, channels):
    """解析M3U格式"""
    entries = content.split("#EXTINF:-1,")
    for entry in entries[1:]:
        parts = entry.split("\n", 1)
        channel_name = parts[0].strip()
        url = parts[1].strip()
        if not _is_blacklisted(url) and _has_valid_ip(url):
            _add_channel(channels, channel_name, url)
    return channels

def _parse_txt(content, channels):
    """解析TXT格式（每行：频道名,URL）"""
    for line in content.splitlines():
        if "," in line:
            name, url = line.split(",", 1)
            name = name.strip()
            url = url.strip()
            if not _is_blacklisted(url) and _has_valid_ip(url):
                _add_channel(channels, name, url)
    return channels

def _add_channel(channels, name, url):
    """统一添加频道，自动去重"""
    if name not in channels:
        channels[name] = []
    if url not in channels[name]:
        channels[name].append(url)

def _is_blacklisted(url):
    """检查黑名单"""
    return any(bl in url for bl in URL_BLACKLIST)

def _has_valid_ip(url):
    """检查有效IP（支持IPv4/IPv6）"""
    return re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\[([0-9a-fA-F:]+)\]", url) is not None
