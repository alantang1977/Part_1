"""解析工具模块"""
import re
from typing import Dict, List
from config import url_blacklist

def parse_template(template_path: str) -> Dict[str, List[str]]:
    """解析频道模板，生成分类-频道列表"""
    categories: Dict[str, List[str]] = {}
    current_category: str = ""
    with open(template_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    categories[current_category] = []
                elif current_category:
                    categories[current_category].append(line.strip())
    return categories

def parse_source_content(content: str, source_type: str) -> Dict[str, List[str]]:
    """解析数据源内容（M3U/TXT）"""
    channels: Dict[str, List[str]] = {}
    if source_type == "m3u":
        return _parse_m3u(content)
    elif source_type == "txt":
        return _parse_txt(content)
    return channels

def _parse_m3u(content: str) -> Dict[str, List[str]]:
    """解析M3U格式"""
    channels: Dict[str, List[str]] = {}
    entries = content.split("#EXTINF:-1,")
    for entry in entries[1:]:
        parts = entry.split("\n", 1)
        if len(parts) == 2:
            channel_name = parts[0].strip()
            url = parts[1].strip()
            if not _is_blacklisted(url) and _has_valid_ip(url):
                _add_channel(channels, channel_name, url)
    return channels

def _parse_txt(content: str) -> Dict[str, List[str]]:
    """解析TXT格式（每行：频道名,URL）"""
    channels: Dict[str, List[str]] = {}
    for line in content.splitlines():
        if "," in line:
            name, url = line.split(",", 1)
            if not _is_blacklisted(url) and _has_valid_ip(url):
                _add_channel(channels, name.strip(), url.strip())
    return channels

def _add_channel(channels: Dict[str, List[str]], name: str, url: str) -> None:
    """统一添加频道，不再区分IP版本"""
    if name not in channels:
        channels[name] = []
    channels[name].append(url)

def _is_blacklisted(url: str) -> bool:
    """检查黑名单"""
    return any(bl in url for bl in url_blacklist)

def _has_valid_ip(url: str) -> bool:
    """检查有效IP"""
    return re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\[([0-9a-fA-F:]+)\]", url) is not None
