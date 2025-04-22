import re
import requests
import logging
from collections import OrderedDict
from config import config, URL_BLACKLIST, LOGO_BASE_URL, EPG_URLS, ANNOUNCEMENTS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("app.log", "w", encoding="utf-8"), logging.StreamHandler()]
)

def parse_template(template_path):
    """解析频道模板文件，生成分类-频道列表"""
    categories = OrderedDict()
    current_category = None
    with open(template_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "#genre#" in line:
                current_category = line.split(",", 1)[0].strip()
                categories[current_category] = []
            elif current_category:
                categories[current_category].append(line.strip())
    return categories

def clean_channel_name(channel_name):
    """清洗频道名称：去除特殊字符并统一大写"""
    cleaned = re.sub(r'[^\w\s-]', '', channel_name)
    cleaned = re.sub(r'\s+', '', cleaned)
    cleaned = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned)
    return cleaned.upper()

def fetch_channels(url):
    """抓取并解析单个数据源的频道数据"""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content = response.text.strip()
        is_m3u = content.startswith("#EXTM3U") or "#EXTINF" in content[:100]
        return parse_source_content(content, "m3u" if is_m3u else "txt")
    except Exception as e:
        logging.error(f"抓取失败 {url}: {str(e)[:50]}")
        return {}

def parse_source_content(content, source_type):
    """解析M3U或TXT格式的数据源"""
    channels = OrderedDict()
    if source_type == "m3u":
        return _parse_m3u(content)
    elif source_type == "txt":
        return _parse_txt(content)
    return channels

def _parse_m3u(content):
    """解析M3U格式内容"""
    entries = content.split("#EXTINF:-1,")
    for entry in entries[1:]:  # 跳过第一个空元素
        parts = entry.split("\n", 1)
        channel_name = parts[0].strip()
        url = parts[1].strip()
        if not _is_blacklisted(url) and _has_valid_ip(url):
            _add_channel(channels, channel_name, url)
    return channels

def _parse_txt(content):
    """解析TXT格式内容（每行：频道名,URL）"""
    for line in content.splitlines():
        if "," in line:
            name, url = line.split(",", 1)
            name = name.strip()
            url = url.strip()
            if not _is_blacklisted(url) and _has_valid_ip(url):
                _add_channel(channels, name, url)
    return channels

def _add_channel(channels, name, url):
    """统一添加频道，去重处理"""
    cleaned_name = clean_channel_name(name)
    if cleaned_name not in channels:
        channels[cleaned_name] = []
    if url not in channels[cleaned_name]:
        channels[cleaned_name].append(url)

def _is_blacklisted(url):
    """检查URL是否在黑名单中"""
    return any(bl in url for bl in URL_BLACKLIST)

def _has_valid_ip(url):
    """检查URL是否包含有效IP地址"""
    return re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|:\w+:\d+", url, re.IGNORECASE) is not None

def match_template_channels(template_categories, all_channels):
    """匹配模板中的频道与抓取到的频道"""
    matched = OrderedDict()
    for category, names in template_categories.items():
        matched[category] = OrderedDict()
        for name in names:
            cleaned_name = clean_channel_name(name)
            if cleaned_name in all_channels:
                matched[category][name] = all_channels[cleaned_name]
    return matched

def generate_m3u(matched_channels):
    """生成标准M3U8格式文件"""
    output = f"#EXTM3U x-tvg-url=\"{'\",\"'.join(EPG_URLS)}\"\n"  # 修复此处引号嵌套问题
    
    # 添加系统公告频道
    for group in ANNOUNCEMENTS:
        for entry in group["entries"]:
            output += (
                f'#EXTINF:-1 tvg-name="{entry["name"]}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{entry["name"]}\n'
                f'{entry["url"]}\n'
            )
    
    # 添加模板频道
    for category, channel_dict in matched_channels.items():
        for channel_name, urls in channel_dict.items():
            for idx, url in enumerate(urls, 1):
                logo_url = f"{LOGO_BASE_URL}{channel_name}.png"
                output += (
                    f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{channel_name}" tvg-logo="{logo_url}" group-title="{category}",{channel_name}\n'
                    f"{url}\n"
                )
    return output

def main():
    template_categories = parse_template("demo.txt")
    all_channels = OrderedDict()
    
    for url in config["source_urls"]:
        logging.info(f"正在处理数据源: {url}")
        new_channels = fetch_channels(url)
        for name, urls in new_channels.items():
            if name in all_channels:
                all_channels[name].extend(urls)
            else:
                all_channels[name] = urls
    
    matched_channels = match_template_channels(template_categories, all_channels)
    m3u_content = generate_m3u(matched_channels)
    
    # 写入输出文件
    output_path = "output/live.m3u"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)
    logging.info(f"成功生成M3U文件: {output_path}")

if __name__ == "__main__":
    main()
