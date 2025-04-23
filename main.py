import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config
import os
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from utils.parser import parse_template, parse_source_content
from logging.handlers import RotatingFileHandler

# 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = RotatingFileHandler(
    "app.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class ChannelManager:
    def __init__(self, template_path):
        self.template_path = template_path
        self.template_channels = parse_template(template_path)  # 解析模板，返回有序字典
        self.all_channels = OrderedDict()  # 存储合并后的频道（有序）
        self.session = self._create_session()  # 创建带连接池和重试的会话

    def _create_session(self):
        """初始化requests会话（带连接池和重试策略）"""
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=requests.packages.urllib3.util.retry.Retry(
                total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
            )
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch_and_merge_channels(self):
        """并发抓取并合并所有数据源频道"""
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._process_source, url) for url in config.SOURCE_URLS]
            for future in futures:
                try:
                    channels = future.result(timeout=60)  # 单个数据源处理超时60秒
                    self._merge_channels(channels)
                except Exception as e:
                    logger.error(f"数据源 {url} 处理失败: {str(e)}", exc_info=False)

    def _process_source(self, url):
        """处理单个数据源（网络请求+格式解析）"""
        try:
            content = self._fetch_url_content(url)
            source_type = self._detect_source_type(content)
            return parse_source_content(content, source_type)
        except Exception as e:
            logger.warning(f"跳过无效数据源 {url}: {str(e)}", exc_info=False)
            return OrderedDict()  # 返回空有序字典

    def _fetch_url_content(self, url):
        """安全获取URL内容（带超时和异常处理）"""
        response = self.session.get(url, timeout=config.NETWORK_CONFIG["timeout"])
        response.raise_for_status()
        return response.text

    def _detect_source_type(self, content):
        """自动检测数据源格式（M3U/TXT）"""
        return "m3u" if any(line.startswith("#EXTINF") for line in content.splitlines()[:15]) else "txt"

    def _merge_channels(self, source_channels):
        """去重合并频道（保留顺序，过滤无效URL）"""
        for name, urls in source_channels.items():
            cleaned_name = self._clean_channel_name(name)
            valid_urls = [
                url for url in urls
                if not self._is_blacklisted(url) and self._has_valid_ip(url)
            ]
            if cleaned_name in self.all_channels:
                # 使用 OrderedDict.fromkeys() 去重并保持顺序
                self.all_channels[cleaned_name] = list(
                    OrderedDict.fromkeys(self.all_channels[cleaned_name] + valid_urls)
                )
            else:
                self.all_channels[cleaned_name] = valid_urls

    def _clean_channel_name(self, name):
        """标准化频道名称（去除特殊字符，转大写）"""
        return re.sub(r'[^\w\s-]', '', name).strip().upper()

    def _is_blacklisted(self, url):
        """正则表达式黑名单检测（不区分大小写）"""
        return any(re.search(bl, url, re.IGNORECASE) for bl in config.URL_BLACKLIST)

    def _has_valid_ip(self, url):
        """检测有效IP地址（支持IPv4/IPv6）"""
        ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ipv6_pattern = r'\[?[0-9a-fA-F:]+\]?'
        return re.search(f"{ipv4_pattern}|{ipv6_pattern}", url) is not None

    def sort_channels_by_speed(self):
        """按响应速度排序（动态线程池+超时控制）"""
        sorted_channels = OrderedDict()
        max_workers = multiprocessing.cpu_count() * 2 + 1  # 动态计算最佳线程数

        for name, urls in self.all_channels.items():
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._check_response_time, url) for url in urls]
                results = []
                for future in futures:
                    try:
                        results.append(future.result(timeout=10))  # 单个URL检测超时10秒
                    except Exception:
                        results.append((url, float('inf')))  # 超时或异常设为最大时间

                # 按响应时间升序排序，过滤掉失败的URL
                sorted_urls = [
                    url for url, time in sorted(results, key=lambda x: x[1])
                    if time != float('inf')
                ]
                sorted_channels[name] = sorted_urls
        return sorted_channels

    def _check_response_time(self, url):
        """高精度响应时间检测（使用HEAD请求，带重定向）"""
        start = datetime.now()
        try:
            self.session.head(url, timeout=5, allow_redirects=True)
            return (url, (datetime.now() - start).microseconds / 1000)
        except Exception:
            return (url, float('inf'))  # 返回无穷大表示失败

    def generate_output_files(self):
        """生成输出文件（M3U/TXT），支持分块写入防内存过载"""
        os.makedirs(config.OUTPUT_CONFIG["output_dir"], exist_ok=True)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(
            f"{config.OUTPUT_CONFIG['output_dir']}/{config.OUTPUT_CONFIG['m3u_filename']}",
            "w", encoding="utf-8"
        ) as m3u, open(
            f"{config.OUTPUT_CONFIG['output_dir']}/{config.OUTPUT_CONFIG['txt_filename']}",
            "w", encoding="utf-8"
        ) as txt:

            self._write_header(m3u, current_time)
            self._write_announcements(m3u, txt)
            self._write_channel_data(m3u, txt)

    def _write_header(self, m3u, current_time):
        """写入M3U文件头部（包含EPG链接和生成信息）"""
        m3u.write(f'#EXTM3U x-tvg-url="{"|".join(config.EPG_URLS)}"\n')
        m3u.write(f'#GENERATOR SuperA/{datetime.now().year}\n')
        m3u.write(f'#LASTUPDATE {current_time}\n\n')

    def _write_announcements(self, m3u, txt):
        """写入系统公告频道（带分组和LOGO）"""
        for group in config.ANNOUNCEMENTS:
            txt.write(f"{group['channel']},#genre#\n")
            for idx, entry in enumerate(group['entries'], 1):
                m3u.write(
                    f'#EXTINF:-1,tvg-id="{idx}",tvg-name="{entry["name"]}",'
                    f'tvg-logo="{entry["logo"]}",group-title="{group["channel"]}"\n'
                )
                m3u.write(f"{entry['url']}\n")
                txt.write(f"{entry['name']},{entry['url']}\n")

    def _write_channel_data(self, m3u, txt):
        """分块写入频道数据（每批100个频道，防止内存过高）"""
        sorted_channels = self.sort_channels_by_speed()
        chunk_size = 100  # 可配置的分块大小

        for category in self.template_channels:
            txt.write(f"{category},#genre#\n")
            channels_in_category = self.template_channels[category]
            for i in range(0, len(channels_in_category), chunk_size):
                chunk = channels_in_category[i:i+chunk_size]
                self._process_chunk(category, chunk, m3u, txt, sorted_channels)

    def _process_chunk(self, category, channel_names, m3u, txt, sorted_channels):
        """处理频道块（去重、排序、写入，带URL去重标记）"""
        written_urls = set()  # 记录已写入的URL，避免重复
        for channel_name in channel_names:
            cleaned_name = self._clean_channel_name(channel_name)
            urls = sorted_channels.get(cleaned_name, [])

            # 去重并按速度排序（使用OrderedDict保持顺序）
            unique_urls = list(OrderedDict.fromkeys(urls))
            sorted_urls = self._sort_by_speed(unique_urls)

            for idx, url in enumerate(sorted_urls, 1):
                if url in written_urls:
                    continue
                self._write_channel_entry(m3u, txt, category, cleaned_name, idx, url)
                written_urls.add(url)  # 标记URL已写入

    def _sort_by_speed(self, urls):
        """带缓存的速度排序（使用线程池并发检测）"""
        with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()*2) as executor:
            results = list(executor.map(self._check_response_time, urls))
        return [url for url, time in sorted(results, key=lambda x: x[1]) if time != float('inf')]

    def _write_channel_entry(self, m3u, txt, category, name, idx, url):
        """标准化频道条目写入（包含LOGO和元数据）"""
        logo = f"{config.LOGO_BASE_URL}{name}.png"
        m3u_line = (
            f'#EXTINF:-1,tvg-id="{idx}",tvg-name="{name}",tvg-logo="{logo}",'
            f'group-title="{category}"\n{url}\n'
        )
        txt_line = f"{name},{url}\n"

        m3u.write(m3u_line)
        txt.write(txt_line)
        # 实时刷新缓冲区，防止内存堆积（重要！）
        m3u.flush()
        txt.flush()

if __name__ == "__main__":
    manager = ChannelManager("demo.txt")
    manager.fetch_and_merge_channels()
    manager.generate_output_files()
    logger.info("频道列表更新完成，文件已生成至output目录")
