"""解析工具模块（处理模板和数据源格式）"""
import re
from config import URL_BLACKLIST
from collections import OrderedDict

def parse_template(template_path: str) -> OrderedDict:
    """解析频道模板文件，返回分类-频道有序字典"""
    with open(template_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    categories = OrderedDict()
    current_category = None
    for line in lines:
        if "#genre#" in line:
            current_category = line.split(",", 1)[0].strip()
            categories[current_category] = []
        elif current_category:
            categories[current_category].append(line.strip())
    return categories

def parse_source_content(content: str, source_type: str) -> OrderedDict:
    """统一解析入口（支持M3U/TXT格式）"""
    parser = {
        "m3u": _parse_m3u,
        "txt": _parse_txt
    }.get(source_type, lambda x: OrderedDict())
    return parser(content)

def _parse_m3u(content: str) -> OrderedDict:
    """解析M3U格式（处理EXTINF标签）"""
    channels = OrderedDict()
    for entry in content.split("#EXTINF:-1,")[1:]:  # 跳过第一个空条目
        name, url = _split_m3u_entry(entry)
        if name and url:
            _add_channel(channels, name, url)
    return channels

def _split_m3u_entry(entry: str) -> tuple:
    """分割M3U条目为名称和URL"""
    parts = entry.split("\n", 1)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""

def _parse_txt(content: str) -> OrderedDict:
    """解析TXT格式（支持#分隔的多个URL）"""
    channels = OrderedDict()
    for line in content.splitlines():
        line = line.strip()
        if not line or "," not in line:
            continue
        name, urls = line.split(",", 1)
        for url in urls.split("#"):
            url = url.strip()
            if url:
                _add_channel(channels, name, url)
    return channels

def _add_channel(channels: OrderedDict, name: str, url: str) -> None:
    """添加频道（标准化名称并去重）"""
    cleaned_name = re.sub(r'[^\w\s-]', '', name).strip().upper()
    if cleaned_name not in channels:
        channels[cleaned_name] = []
    if url not in channels[cleaned_name]:
        channels[cleaned_name].append(url)

def _is_blacklisted(url: str) -> bool:
    """正则表达式黑名单检测"""
    return any(re.search(bl, url, re.IGNORECASE) for bl in URL_BLACKLIST)

def _has_valid_ip(url: str) -> bool:
    """检测有效IP地址（支持IPv4/IPv6）"""
    ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    ipv6_pattern = r'\[?[0-9a-fA-F:]+\]?'
    return re.search(f"{ipv4_pattern}|{ipv6_pattern}", url) is not None
