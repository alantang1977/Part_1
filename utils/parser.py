"""直播源解析工具集"""
import re
from config import config
from typing import Dict, List, Tuple

def parse_template(template_path: str) -> Dict[str, List[str]]:
    """解析频道模板文件，生成分类-频道名映射
    :param template_path: 模板文件路径
    :return: 分类字典 {category: [channel_names]}
    """
    template = {}
    current_category = None
    with open(template_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "#genre#" in line:
                current_category = line.split(",")[0].strip()
                template[current_category] = []
            elif current_category:
                template[current_category].append(line.strip())
    return template

def parse_source(content: str, source_type: str) -> Dict[str, List[str]]:
    """解析数据源内容（M3U/TXT）
    :param content: 数据源内容
    :param source_type: 格式类型（m3u/txt）
    :return: 频道字典 {channel_name: [urls]}
    """
    if source_type == "m3u":
        return _parse_m3u(content)
    elif source_type == "txt":
        return _parse_txt(content)
    return {}

def _parse_m3u(content: str) -> Dict[str, List[str]]:
    """解析M3U格式内容
    提取#EXTINF后的频道名和URL，自动去重并过滤黑名单
    """
    channels = {}
    entries = content.split("#EXTINF:-1,")
    for entry in entries[1:]:  # 跳过第一个空元素
        try:
            name, url = entry.split("\n", 1)
            url = url.strip()
            if _is_valid_url(url) and not _is_blacklisted(url):
                _add_channel(channels, name.strip(), url)
        except ValueError:
            continue  # 忽略格式错误的条目
    return channels

def _parse_txt(content: str) -> Dict[str, List[str]]:
    """解析TXT格式内容（每行：频道名,URL）"""
    channels = {}
    for line in content.splitlines():
        if "," not in line:
            continue
        try:
            name, url = line.split(",", 1)
            url = url.strip()
            if _is_valid_url(url) and not _is_blacklisted(url):
                _add_channel(channels, name.strip(), url)
        except ValueError:
            continue
    return channels

def _add_channel(channels: Dict, name: str, url: str):
    """统一频道添加逻辑（自动去重）"""
    if name not in channels:
        channels[name] = []
    if url not in channels[name]:
        channels[name].append(url)

def _is_blacklisted(url: str) -> bool:
    """检查URL是否匹配黑名单（支持正则）"""
    return any(re.search(bl, url) for bl in config.url_blacklist)

def _is_valid_url(url: str) -> bool:
    """验证URL是否包含有效IP（支持IPv4/IPv6）"""
    ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b|^\[?[0-9a-fA-F:]+\]?"
    return re.search(ip_pattern, url, re.IGNORECASE) is not None
