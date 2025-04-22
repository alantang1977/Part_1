import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config


# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("function.log", "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)


def parse_template(template_file):
    """解析模板文件，提取频道分类和名称"""
    template_channels = OrderedDict()
    current_category = None

    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)
    return template_channels


def clean_channel_name(channel_name):
    """清洗频道名称（去除特殊字符并统一大写）"""
    cleaned_name = re.sub(r'[$「」-]', '', channel_name)
    cleaned_name = re.sub(r'\s+', '', cleaned_name)
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)
    return cleaned_name.upper()


def fetch_channels(url):
    """从URL抓取频道列表并解析"""
    channels = OrderedDict()
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        lines = response.text.split("\n")
        is_m3u = any(line.startswith("#EXTINF") for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"成功获取 {url}，判断为 {source_type} 格式")

        if is_m3u:
            channels = parse_m3u_lines(lines)
        else:
            channels = parse_txt_lines(lines)

        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"{url} 包含频道分类: {categories}")
    except requests.RequestException as e:
        logging.error(f"获取 {url} 失败: {str(e)}")
    return channels


def parse_m3u_lines(lines):
    """解析M3U格式内容"""
    channels = OrderedDict()
    current_category = None
    current_channel_name = None

    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                current_channel_name = match.group(2).strip()
                if current_channel_name.startswith("CCTV"):
                    current_channel_name = clean_channel_name(current_channel_name)
                if current_category not in channels:
                    channels[current_category] = []
        elif line and not line.startswith("#"):
            if current_category and current_channel_name:
                channels[current_category].append((current_channel_name, line.strip()))
    return channels


def parse_txt_lines(lines):
    """解析TXT格式内容（每行频道名,URL）"""
    channels = OrderedDict()
    current_category = None

    for line in lines:
        line = line.strip()
        if "#genre#" in line:
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
        elif current_category and "," in line:
            channel_name, url = line.split(",", 1)
            channel_name = clean_channel_name(channel_name.strip())
            for u in url.strip().split('#'):
                if u:
                    channels[current_category].append((channel_name, u.strip()))
    return channels


def match_channels(template_channels, all_channels):
    """匹配模板频道与抓取到的频道"""
    matched_channels = OrderedDict()
    for t_category, t_channels in template_channels.items():
        matched_channels[t_category] = OrderedDict()
        for t_name in t_channels:
            for a_category, a_channel_list in all_channels.items():
                for a_name, a_url in a_channel_list:
                    if t_name == a_name:
                        matched_channels[t_category].setdefault(t_name, []).append(a_url)
    return matched_channels


def filter_source_urls(template_file):
    """过滤并合并源URL的频道信息"""
    template_channels = parse_template(template_file)
    all_channels = OrderedDict()
    for url in config.source_urls:
        merged_channels = fetch_channels(url)
        merge_channels(all_channels, merged_channels)
    return match_channels(template_channels, all_channels), template_channels


def merge_channels(target, source):
    """合并两个频道字典"""
    for category, channel_list in source.items():
        if category in target:
            target[category].extend(channel_list)
        else:
            target[category] = channel_list


def is_ipv6(url):
    """判断URL是否包含IPv6地址"""
    return re.match(r'^https?://\[[0-9a-fA-F:]+\]', url, re.IGNORECASE) is not None


def update_channel_urls(channels, template_channels):
    """更新频道URL到M3U和TXT文件"""
    written_ipv4 = set()
    written_ipv6 = set()
    current_date = datetime.now().strftime("%Y-%m-%d")

    # 处理公告信息（设置动态日期）
    for group in config.announcements:
        for entry in group['entries']:
            if entry['name'] is None:
                entry['name'] = current_date

    # 生成EPG URL列表（带双引号）
    epg_quoted = [f'"{url}"' for url in config.epg_urls]

    with open("live_ipv4.m3u", "w", encoding="utf-8") as m3u4, \
         open("live_ipv4.txt", "w", encoding="utf-8") as txt4, \
         open("live_ipv6.m3u", "w", encoding="utf-8") as m3u6, \
         open("live_ipv6.txt", "w", encoding="utf-8") as txt6:

        # 写入M3U头部（修复后的EPG URL拼接）
        m3u4.write(f'#EXTM3U x-tvg-url={",".join(epg_quoted)}\n')
        m3u6.write(f'#EXTM3U x-tvg-url={",".join(epg_quoted)}\n')

        # 写入系统公告
        _write_announcements(m3u4, txt4, m3u6, txt6, current_date)

        # 写入频道内容
        _write_channels(channels, template_channels, m3u4, txt4, m3u6, txt6, written_ipv4, written_ipv6)


def _write_announcements(m3u4, txt4, m3u6, txt6, current_date):
    """辅助函数：写入系统公告"""
    for group in config.announcements:
        txt4.write(f"{group['channel']},#genre#\n")
        txt6.write(f"{group['channel']},#genre#\n")
        for entry in group['entries']:
            name = entry['name'] or current_date
            m3u4.write(f'#EXTINF:-1 tvg-id="1" tvg-name="{name}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{name}\n')
            m3u4.write(f"{entry['url']}\n")
            txt4.write(f"{name},{entry['url']}\n")

            m3u6.write(f'#EXTINF:-1 tvg-id="1" tvg-name="{name}" tvg-logo="{entry["logo"]}" group-title="{group["channel"]}",{name}\n')
            m3u6.write(f"{entry['url']}\n")
            txt6.write(f"{name},{entry['url']}\n")


def _write_channels(channels, template_channels, m3u4, txt4, m3u6, txt6, written_ipv4, written_ipv6):
    """辅助函数：写入频道内容"""
    for category, channel_list in template_channels.items():
        txt4.write(f"{category},#genre#\n")
        txt6.write(f"{category},#genre#\n")
        if category in channels:
            for channel_name in channel_list:
                if channel_name in channels[category]:
                    _process_channel_ips(
                        category,
                        channel_name,
                        channels[category][channel_name],
                        m3u4, txt4, written_ipv4, "IPV4",
                        m3u6, txt6, written_ipv6, "IPV6"
                    )


def _process_channel_ips(category, channel_name, urls, m3u4, txt4, written4, ip4, m3u6, txt6, written6, ip6):
    """辅助函数：处理IPv4和IPv6地址的URL"""
    # 过滤并排序IPv4 URL
    ipv4_urls = [u for u in sort_and_filter_urls(urls, written4) if not is_ipv6(u)]
    for idx, url in enumerate(ipv4_urls, 1):
        new_url = add_url_suffix(url, idx, len(ipv4_urls), ip4)
        _write_to_file(m3u4, txt4, category, channel_name, idx, new_url)

    # 过滤并排序IPv6 URL
    ipv6_urls = [u for u in sort_and_filter_urls(urls, written6) if is_ipv6(u)]
    for idx, url in enumerate(ipv6_urls, 1):
        new_url = add_url_suffix(url, idx, len(ipv6_urls), ip6)
        _write_to_file(m3u6, txt6, category, channel_name, idx, new_url)


def sort_and_filter_urls(urls, written_set):
    """排序并过滤URL（去重、去黑名单）"""
    priority = config.ip_version_priority.lower() == "ipv6"
    sorted_urls = sorted(urls, key=lambda u: not is_ipv6(u) if priority else is_ipv6(u))
    return [u for u in sorted_urls if u and u not in written_set and not _is_blacklisted(u)]


def _is_blacklisted(url):
    """检查URL是否在黑名单中（使用config中的全局黑名单）"""
    return any(bl in url for bl in config.url_blacklist)


def add_url_suffix(url, index, total, ip_version):
    """为URL添加后缀（线路编号）"""
    suffix = f"${ip_version}" if total == 1 else f"${ip_version}•线路{index}"
    base = url.split('$', 1)[0] if '$' in url else url
    return f"{base}{suffix}"


def _write_to_file(m3u_file, txt_file, category, name, idx, url):
    """辅助函数：写入单个频道到文件"""
    logo = f"https://gitee.com/IIII-9306/PAV/raw/master/logos/{name}.png"
    m3u_file.write(f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}\n')
    m3u_file.write(f"{url}\n")
    txt_file.write(f"{name},{url}\n")


if __name__ == "__main__":
    template = "demo.txt"
    matched, tmpl = filter_source_urls(template)
    update_channel_urls(matched, tmpl)
    logging.info("频道列表更新完成")
