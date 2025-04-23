import re
from config import URL_BLACKLIST

def parse_template(template_path):
    """解析模板文件（支持分类和频道层级）"""
    template_channels = OrderedDict()
    with open(template_path, "r", encoding="utf-8") as f:
        current_category = None
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "#genre#" in line:
                current_category = line.split(",")[0].strip()
                template_channels[current_category] = []
            elif current_category:
                template_channels[current_category].append(line.strip())
    return template_channels

def parse_source_content(content, source_type):
    """统一解析入口（支持M3U/TXT格式）"""
    channels = OrderedDict()
    if source_type == "m3u":
        return _parse_m3u(content)
    elif source_type == "txt":
        return _parse_txt(content)
    return channels

def _parse_m3u(content):
    """高效解析M3U格式（处理EXTINF标签）"""
    entries = content.split("#EXTINF:-1,")
    for entry in entries[1:]:
        name, url = _split_m3u_entry(entry)
        if name and url and not _is_blacklisted(url) and _has_valid_ip(url):
            _add_channel(channels, name, url)
    return channels

def _split_m3u_entry(entry):
    """分割M3U条目（处理复杂标签）"""
    parts = entry.split("\n", 1)
    name = parts[0].strip()
    url = parts[1].strip() if len(parts) > 1 else ""
    return name, url

def _parse_txt(content):
    """解析TXT格式（处理多URL分隔符）"""
    for line in content.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        name, url = line.split(",", 1)
        for u in url.split("#"):  # 支持#分隔的多个URL
            u = u.strip()
            if u and not _is_blacklisted(u) and _has_valid_ip(u):
                _add_channel(channels, name, u)
    return channels

def _add_channel(channels, name, url):
    """线程安全的频道添加（保持顺序）"""
    cleaned_name = re.sub(r'[^\w\s-]', '', name).strip().upper()
    if cleaned_name not in channels:
        channels[cleaned_name] = []
    channels[cleaned_name].append(url)

def _is_blacklisted(url):
    """正则表达式黑名单检测（支持IPv6地址过滤）"""
    return any(re.search(bl, url, re.IGNORECASE) for bl in URL_BLACKLIST)

def _has_valid_ip(url):
    """同时支持IPv4和IPv6地址检测"""
    ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    ipv6_pattern = r'\[([0-9a-fA-F:]+)\]'
    return re.search(f"{ipv4_pattern}|{ipv6_pattern}", url) is not None
