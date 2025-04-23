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

# 日志系统配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# 文件日志处理器（10MB单个文件，5个备份）
file_handler = RotatingFileHandler(
    "app.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 控制台日志处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class ChannelManager:
    def __init__(self, template_path):
        self.template_path = template_path
        self.template_channels = parse_template(template_path)  # 解析模板文件
        self.all_channels = OrderedDict()  # 存储合并后的频道（保持顺序）
        self.session = self._create_session()  # 初始化带重试的会话

    def _create_session(self) -> requests.Session:
        """创建带连接池和重试策略的requests会话"""
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=requests.packages.urllib3.util.retry.Retry(
                total=config.NETWORK_CONFIG["max_retries"],
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504]
            )
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def fetch_and_merge_channels(self) -> None:
        """并发抓取多数据源并合并频道数据"""
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._process_source, url) for url in config.SOURCE_URLS]
            for future in futures:
                try:
                    channels = future.result(timeout=60)
                    self._merge_channels(channels)
                except Exception as e:
                    logger.error(f"数据源处理失败: {str(e)}", exc_info=False)

    def _process_source(self, url: str) -> OrderedDict:
        """处理单个数据源（网络请求+格式解析）"""
        try:
            content = self._fetch_url_content(url)
            source_type = self._detect_source_type(content)
            return parse_source_content(content, source_type)
        except Exception as e:
            logger.warning(f"跳过无效数据源 {url}: {str(e)}", exc_info=False)
            return OrderedDict()

    def _fetch_url_content(self, url: str) -> str:
        """安全获取URL内容（带超时和异常处理）"""
        response = self.session.get(url, timeout=config.NETWORK_CONFIG["timeout"])
        response.raise_for_status()
        return response.text

    def _detect_source_type(self, content: str) -> str:
        """自动检测数据源格式（M3U/TXT）"""
        return "m3u" if any(line.startswith("#EXTINF") for line in content.splitlines()[:15]) else "txt"

    def _merge_channels(self, source_channels: OrderedDict) -> None:
        """去重合并频道（保留顺序并过滤无效URL）"""
        for name, urls in source_channels.items():
            cleaned_name = self._clean_channel_name(name)
            valid_urls = [
                url for url in urls
                if not self._is_blacklisted(url) and self._has_valid_ip(url)
            ]
            if cleaned_name in self.all_channels:
                # 使用OrderedDict去重并保持顺序
                self.all_channels[cleaned_name] = list(
                    OrderedDict.fromkeys(self.all_channels[cleaned_name] + valid_urls)
                )
            else:
                self.all_channels[cleaned_name] = valid_urls

    def _clean_channel_name(self, name: str) -> str:
        """标准化频道名称（去除特殊字符并转大写）"""
        return re.sub(r'[^\w\s-]', '', name).strip().upper()

    def _is_blacklisted(self, url: str) -> bool:
        """正则表达式黑名单检测（不区分大小写）"""
        return any(re.search(bl, url, re.IGNORECASE) for bl in config.URL_BLACKLIST)

    def _has_valid_ip(self, url: str) -> bool:
        """检测有效IP地址（支持IPv4/IPv6）"""
        ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ipv6_pattern = r'\[?[0-9a-fA-F:]+\]?'
        return re.search(f"{ipv4_pattern}|{ipv6_pattern}", url) is not None

    def sort_channels_by_speed(self) -> OrderedDict:
        """按响应速度排序频道（动态线程池+超时控制）"""
        sorted_channels = OrderedDict()
        max_workers = multiprocessing.cpu_count() * 2 + 1  # 动态计算最佳线程数

        for channel_name, urls in self.all_channels.items():
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 建立URL与Future的显式映射
                url_futures = [(url, executor.submit(self._check_response_time, url)) for url in urls]
                results = []
                for current_url, future in url_futures:
                    try:
                        response_time = future.result(timeout=10)
                        results.append((current_url, response_time))
                    except Exception as e:
                        logger.debug(f"URL {current_url} 检测超时: {str(e)}")
                        results.append((current_url, float('inf')))

                # 按响应时间升序排序并过滤无效URL
                sorted_results = sorted(results, key=lambda x: x[1])
                valid_urls = [url for url, time in sorted_results if time != float('inf')]
                sorted_channels[channel_name] = valid_urls
        return sorted_channels

    def _check_response_time(self, url: str) -> float:
        """高精度响应时间检测（使用HEAD请求）"""
        start = datetime.now()
        try:
            self.session.head(url, timeout=5, allow_redirects=True)
            return (datetime.now() - start).microseconds / 1000
        except Exception as e:
            logger.debug(f"URL {url} 连接失败: {str(e)}")
            return float('inf')

    def generate_output_files(self) -> None:
        """生成M3U和TXT格式的输出文件（支持分块写入）"""
        os.makedirs(config.OUTPUT_CONFIG["output_dir"], exist_ok=True)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(
            f"{config.OUTPUT_CONFIG['output_dir']}/{config.OUTPUT_CONFIG['m3u_filename']}",
            "w", encoding="utf-8"
        ) as m3u_file, open(
            f"{config.OUTPUT_CONFIG['output_dir']}/{config.OUTPUT_CONFIG['txt_filename']}",
            "w", encoding="utf-8"
        ) as txt_file:

            self._write_m3u_header(m3u_file, current_time)
            self._write_announcements(m3u_file, txt_file)
            self._write_channel_data(m3u_file, txt_file)

    def _write_m3u_header(self, m3u_file, current_time: str) -> None:
        """写入M3U文件头部信息（包含EPG链接）"""
        m3u_file.write(f'#EXTM3U x-tvg-url="{"|".join(config.EPG_URLS)}"\n')
        m3u_file.write(f'#GENERATOR SuperA/{datetime.now().year}\n')
        m3u_file.write(f'#LASTUPDATE {current_time}\n\n')

    def _write_announcements(self, m3u_file, txt_file) -> None:
        """写入系统公告频道（带分组和LOGO信息）"""
        for group in config.ANNOUNCEMENTS:
            txt_file.write(f"{group['channel']},#genre#\n")
            for idx, entry in enumerate(group['entries'], 1):
                m3u_file.write(
                    f'#EXTINF:-1,tvg-id="{idx}",tvg-name="{entry["name"]}",'
                    f'tvg-logo="{entry["logo"]}",group-title="{group["channel"]}"\n'
                )
                m3u_file.write(f"{entry['url']}\n")
                txt_file.write(f"{entry['name']},{entry['url']}\n")

    def _write_channel_data(self, m3u_file, txt_file) -> None:
        """分块写入频道数据（防止内存过载）"""
        sorted_channels = self.sort_channels_by_speed()
        chunk_size = 100  # 每批处理100个频道

        for category in self.template_channels:
            txt_file.write(f"{category},#genre#\n")
            channel_names = self.template_channels[category]
            for i in range(0, len(channel_names), chunk_size):
                self._process_channel_chunk(category, channel_names[i:i+chunk_size], m3u_file, txt_file, sorted_channels)

    def _process_channel_chunk(
        self,
        category: str,
        channel_names: list,
        m3u_file,
        txt_file,
        sorted_channels: OrderedDict
    ) -> None:
        """处理频道块（去重、排序、写入）"""
        written_urls = set()  # 记录已写入的URL避免重复
        for channel_name in channel_names:
            cleaned_name = self._clean_channel_name(channel_name)
            urls = sorted_channels.get(cleaned_name, [])

            # 去重并按速度排序
            unique_urls = list(OrderedDict.fromkeys(urls))
            sorted_urls = self._sort_by_speed(unique_urls)

            for idx, url in enumerate(sorted_urls, 1):
                if url in written_urls:
                    continue
                self._write_channel_entry(m3u_file, txt_file, category, cleaned_name, idx, url)
                written_urls.add(url)

    def _sort_by_speed(self, urls: list) -> list:
        """带缓存的速度排序（使用线程池并发检测）"""
        with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()*2) as executor:
            results = list(executor.map(self._check_response_time, urls))
        return [url for url, time in sorted(zip(urls, results), key=lambda x: x[1]) if time != float('inf')]

    def _write_channel_entry(
        self,
        m3u_file,
        txt_file,
        category: str,
        name: str,
        idx: int,
        url: str
    ) -> None:
        """写入标准化频道条目（包含LOGO和元数据）"""
        logo = f"{config.LOGO_BASE_URL}{name}.png"
        m3u_entry = (
            f'#EXTINF:-1,tvg-id="{idx}",tvg-name="{name}",tvg-logo="{logo}",'
            f'group-title="{category}"\n{url}\n'
        )
        txt_entry = f"{name},{url}\n"

        m3u_file.write(m3u_entry)
        txt_file.write(txt_entry)
        # 实时刷新缓冲区防止内存堆积
        m3u_file.flush()
        txt_file.flush()

if __name__ == "__main__":
    manager = ChannelManager("demo.txt")
    manager.fetch_and_merge_channels()
    manager.generate_output_files()
    logger.info("频道列表更新完成，文件已生成至output目录")
