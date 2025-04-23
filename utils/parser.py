"""通用解析工具模块"""
import re
from collections import OrderedDict
from config import SOURCE_CONFIG

class Parser:
    """统一解析接口"""
    @staticmethod
    def parse_template(template_path: str) -> OrderedDict:
        """解析频道模板文件"""
        template_channels = OrderedDict()
        with open(template_path, "r", encoding="utf-8") as f:
            current_category = None
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

    @staticmethod
    def parse_source(content: str, source_type: str) -> OrderedDict:
        """解析数据源内容（M3U/TXT）"""
        parser = {
            "m3u": Parser._parse_m3u,
            "txt": Parser._parse_txt
        }.get(source_type, lambda _: OrderedDict())
        return parser(content)

    @staticmethod
    def _parse_m3u(content: str) -> OrderedDict:
        """解析M3U格式"""
        channels = OrderedDict()
        for entry in content.split("#EXTINF:-1,"):
            if not entry:
                continue
            name, url = entry.split("\n", 1)
            name = name.strip()
            url = url.strip()
            if not Parser._is_blacklisted(url) and Parser._has_valid_ip(url):
                channels[name] = channels.get(name, []) + [url]
        return channels

    @staticmethod
    def _parse_txt(content: str) -> OrderedDict:
        """解析TXT格式（每行：频道名,URL）"""
        channels = OrderedDict()
        for line in content.splitlines():
            if "," not in line:
                continue
            name, url = line.split(",", 1)
            name = name.strip()
            url = url.strip()
            if not Parser._is_blacklisted(url) and Parser._has_valid_ip(url):
                channels[name] = channels.get(name, []) + [url]
        return channels

    @staticmethod
    def _is_blacklisted(url: str) -> bool:
        """检查URL黑名单"""
        return any(bl in url for bl in SOURCE_CONFIG["url_blacklist"])

    @staticmethod
    def _has_valid_ip(url: str) -> bool:
        """检查有效IP（支持IPv4/IPv6）"""
        ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b|(\[?[0-9a-fA-F:]+\]?)"
        return re.search(ip_pattern, url) is not None
