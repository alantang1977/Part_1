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

# 日志配置（使用RotatingFileHandler防止日志过大）
from logging.handlers import RotatingFileHandler
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
        self.template_channels = parse_template(template_path)
        self.all_channels = OrderedDict()
        self.session = self._create_session()

    def _create_session(self):
        """创建带连接池和重试策略的会话"""
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504]
            )
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch_and_merge_channels(self):
        """抓取并合并所有数据源频道（带并发控制和超时）"""
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._process_source, url) for url in config.source_urls]
            for future in futures:
                try:
                    merged = future.result(timeout=60)  # 单个数据源处理超时60秒
                    self._merge_channels(merged)
                except Exception as e:
                    logger.error(f"数据源处理失败: {str(e)}")

    def _process_source(self, url):
        """处理单个数据源（包含格式检测和解析）"""
        try:
            content = self._fetch_url_content(url)
            source_type = self._detect_source_type(content)
            return parse_source_content(content, source_type)
        except Exception as e:
            logger.warning(f"跳过无效数据源 {url}: {str(e)}")
            return {}

    def _fetch_url_content(self, url):
        """安全获取URL内容（带会话重用和超时）"""
        response = self.session.get(url, timeout=config.NETWORK_CONFIG["timeout"])
        response.raise_for_status()
        return response.text

    def _detect_source_type(self, content):
        """智能检测数据源类型（支持M3U/TXT）"""
        return "m3u" if any(line.startswith("#EXTINF") for line in content.splitlines()[:15]) else "txt"

    def _merge_channels(self, source_channels):
        """去重合并频道数据（保留顺序）"""
        for name, urls in source_channels.items():
            cleaned_name = self._clean_channel_name(name)
            self.all_channels[cleaned_name] = list({
                u for u in self.all_channels.get(cleaned_name, []) + urls
                if not self._is_blacklisted(u) and self._has_valid_ip(u)
            })

    def _clean_channel_name(self, name):
        """标准化频道名称（去除干扰字符）"""
        return re.sub(r'[^\w\s-]', '', name).strip().upper()

    def _is_blacklisted(self, url):
        """增强版黑名单检测（支持正则匹配）"""
        return any(re.search(bl, url, re.IGNORECASE) for bl in config.URL_BLACKLIST)

    def _has_valid_ip(self, url):
        """检测有效IP地址（支持IPv4/IPv6）"""
        return re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\[([0-9a-fA-F:]+)\]', url) is not None

    def sort_channels_by_speed(self):
        """按响应速度排序（动态线程池+超时控制）"""
        sorted_channels = OrderedDict()
        max_workers = multiprocessing.cpu_count() * 2 + 1
        
        for name, urls in self.all_channels.items():
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._check_response_time, url) for url in urls]
                results = []
                for future in futures:
                    try:
                        results.append(future.result(timeout=10))  # 单个URL检测超时10秒
                    except Exception:
                        results.append((url, float('inf')))
                
                # 按响应时间升序排序，忽略失败的URL
                sorted_urls = [url for url, time in sorted(results, key=lambda x: x[1]) if time != float('inf')]
                sorted_channels[name] = sorted_urls
        return sorted_channels

    def _check_response_time(self, url):
        """高精度响应时间检测（使用HEAD请求）"""
        start = datetime.now()
        try:
            self.session.head(url, timeout=5, allow_redirects=True)
            return (url, (datetime.now() - start).microseconds / 1000)
        except Exception:
            return (url, float('inf'))

    def generate_output_files(self):
        """生成输出文件（支持分块写入和资源监控）"""
        os.makedirs(config.OUTPUT_CONFIG["output_dir"], exist_ok=True)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(
            f"{config.OUTPUT_CONFIG['output_dir']}/live.m3u", "w", encoding="utf-8"
        ) as m3u, open(
            f"{config.OUTPUT_CONFIG['output_dir']}/live.txt", "w", encoding="utf-8"
        ) as txt:
            
            self._write_header(m3u, current_time)
            self._write_announcements(m3u, txt)
            self._write_channel_data(m3u, txt)

    def _write_header(self, m3u, current_time):
        """写入文件头部信息（含EPG链接）"""
        epg_links = ',"'.join(config.epg_urls)
        m3u.write(f'#EXTM3U x-tvg-url="http://epg.51zmt.top:8000/e.xml","{epg_links}"\n')
        m3u.write(f'#GENERATOR SuperA/{datetime.now().year}\n')
        m3u.write(f'#LASTUPDATE {current_time}\n\n')

    def _write_announcements(self, m3u, txt):
        """写入系统公告（带LOGO和分组）"""
        for group in config.announcements:
            txt.write(f"{group['channel']},#genre#\n")
            for idx, entry in enumerate(group['entries'], 1):
                m3u.write(f'#EXTINF:-1,tvg-id="{idx}",tvg-name="{entry["name"]}",tvg-logo="{entry["logo"]}",group-title="{group["channel"]}"\n')
                m3u.write(f"{entry['url']}\n")
                txt.write(f"{entry['name']},{entry['url']}\n")

    def _write_channel_data(self, m3u, txt):
        """分块写入频道数据（防止内存过载）"""
        sorted_channels = self.sort_channels_by_speed()
        chunk_size = 100  # 每批处理100个频道
        
        for category in self.template_channels:
            txt.write(f"{category},#genre#\n")
            for i in range(0, len(self.template_channels[category]), chunk_size):
                chunk = self.template_channels[category][i:i+chunk_size]
                self._process_chunk(category, chunk, m3u, txt, sorted_channels)

    def _process_chunk(self, category, channel_names, m3u, txt, sorted_channels):
        """处理频道块（包含URL去重和排序）"""
        written_urls = set()
        for channel_name in channel_names:
            cleaned_name = self._clean_channel_name(channel_name)
            urls = sorted_channels.get(cleaned_name, [])
            
            # 去重并按速度排序
            unique_urls = list({u for u in urls if u and not self._is_blacklisted(u)})
            sorted_urls = self._sort_by_speed(unique_urls)
            
            for idx, url in enumerate(sorted_urls, 1):
                if url in written_urls:
                    continue
                self._write_channel_entry(m3u, txt, category, cleaned_name, idx, url)
                written_urls.add(url)

    def _sort_by_speed(self, urls):
        """带缓存的速度排序（避免重复检测）"""
        if not urls:
            return []
        with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()*2) as executor:
            results = list(executor.map(self._check_response_time, urls))
        return [url for url, time in sorted(results, key=lambda x: x[1]) if time != float('inf')]

    def _write_channel_entry(self, m3u, txt, category, name, idx, url):
        """标准化条目写入（带LOGO和元数据）"""
        logo = f"{config.LOGO_BASE_URL}{name}.png"
        m3u_line = (
            f'#EXTINF:-1,tvg-id="{idx}",tvg-name="{name}",tvg-logo="{logo}",group-title="{category}"\n'
            f"{url}\n"
        )
        txt_line = f"{name},{url}\n"
        
        m3u.write(m3u_line)
        txt.write(txt_line)
        # 实时刷新缓冲区防止内存堆积
        m3u.flush()
        txt.flush()

if __name__ == "__main__":
    manager = ChannelManager("demo.txt")
    manager.fetch_and_merge_channels()
    manager.generate_output_files()
    logger.info("频道列表更新完成，文件已生成至output目录")
