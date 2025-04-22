import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
from utils.parser import parse_template, parse_source_content

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_channel_name(channel_name):
    """清洗频道名称"""
    return re.sub(r'[^\w\s-]', '', channel_name).strip().upper()

def fetch_channels(url):
    """抓取频道数据"""
    try:
        response = requests.get(url)
        response.encoding = 'utf-8'
        is_m3u = any(line.startswith("#EXTINF") for line in response.text.split("\n")[:15])
        source_type = "m3u" if is_m3u else "txt"
        return parse_source_content(response.text, source_type)
    except Exception as e:
        logging.error(f"抓取失败: {url}, 错误: {e}")
        return {}

def merge_channels(all_channels, new_channels):
    """合并频道数据"""
    for name, urls in new_channels.items():
        if name in all_channels:
            all_channels[name].extend(urls)
        else:
            all_channels[name] = urls

def match_template_channels(template_channels, all_channels):
    """匹配模板频道"""
    matched = OrderedDict()
    for category, names in template_channels.items():
        matched[category] = OrderedDict()
        for name in names:
            if name in all_channels:
                matched[category][name] = list(set(all_channels[name]))  # 去重
    return matched

def generate_m3u(channels):
    """生成M3U文件"""
    output = f"#EXTM3U x-tvg-url={','.join(f'"{u}"' for u in config.epg_urls)}\n"
    
    # 添加公告频道
    for group in config.announcements:
        for entry in group['entries']:
            output += f'#EXTINF:-1 tvg-name="{entry["name"]}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{entry["name"]}\n'
            output += f'{entry["url"]}\n'
    
    # 添加模板频道
    for category, channel_dict in channels.items():
        for channel_name, urls in channel_dict.items():
            for idx, url in enumerate(urls, 1):
                logo_url = f"{config.LOGO_BASE_URL}{channel_name}.png"
                output += f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{channel_name}" tvg-logo="{logo_url}" group-title="{category}",{channel_name}\n'
                output += f"{url}\n"
    
    return output

def main():
    template_channels = parse_template("demo.txt")
    all_channels = OrderedDict()
    
    for url in config.source_urls:
        logging.info(f"正在抓取: {url}")
        new_channels = fetch_channels(url)
        merge_channels(all_channels, new_channels)
    
    matched_channels = match_template_channels(template_channels, all_channels)
    m3u_content = generate_m3u(matched_channels)
    
    # 写入输出文件夹
    output_path = "output/live.m3u"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)
    logging.info(f"成功生成M3U文件: {output_path}")

if __name__ == "__main__":
    main()
