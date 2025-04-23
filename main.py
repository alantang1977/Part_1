"""直播源处理核心逻辑"""
import re
import asyncio
import aiohttp
import logging
from dataclasses import asdict
from collections import OrderedDict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import config, AppConfig
from utils.parser import parse_template, parse_source

# 日志配置（区分文件和控制台输出）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler("app.log", "a", "utf-8"),
        logging.StreamHandler()
    ]
)

class ChannelProcessor:
    """频道处理核心类"""
    def __init__(self):
        self.template_channels = {}
        self.all_channels = OrderedDict()  # 存储所有来源的频道
        self.matched_channels = OrderedDict()  # 匹配模板后的频道

    async def fetch_source(self, session: aiohttp.ClientSession, url: str):
        """异步获取单个数据源内容
        :param session: aiohttp客户端会话
        :param url: 数据源URL
        :return: 解析后的频道字典
        """
        retries = 3
        for attempt in range(retries):
            try:
                async with session.get(url, timeout=15) as response:
                    content = await response.text(encoding="utf-8")
                    source_type = "m3u" if "#EXTINF" in content[:200] else "txt"
                    return {url: parse_source(content, source_type)}
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logging.warning(f"源{url}第{attempt+1}次获取失败: {str(e)}")
        return {}  # 所有重试失败

    def check_response_time(self, url: str) -> Tuple[str, float]:
        """检测URL响应时间（使用GET请求，兼容不支持HEAD的服务器）
        :param url: 待检测URL
        :return: (url, 响应时间ms)
        """
        try:
            start = datetime.now()
            # 使用流式请求避免下载完整内容
            with requests.get(url, stream=True, timeout=10) as response:
                response.raise_for_status()
            return (url, (datetime.now() - start).total_seconds() * 1000)
        except Exception as e:
            logging.warning(f"检测{url}响应时间失败: {str(e)}")
            return (url, float('inf'))

    def process_template(self, template_path: str):
        """处理频道模板文件
        :param template_path: 模板文件路径
        """
        self.template_channels = parse_template(template_path)
        logging.info(f"加载模板成功，包含{len(self.template_channels)}个分类")

    async def process_sources(self):
        """异步处理所有数据源"""
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_source(session, url) for url in config.source_urls]
            results = await asyncio.gather(*tasks)
            for res in results:
                if res:
                    for source_url, chans in res.items():
                        self.merge_channels(chans, source_url)

    def merge_channels(self, source_channels: Dict, source_url: str):
        """合并多源频道数据（添加来源标记）
        :param source_channels: 单源频道数据
        :param source_url: 数据源URL
        """
        source_name = source_url.split("/")[-1]  # 提取来源标识
        for name, urls in source_channels.items():
            if name not in self.all_channels:
                self.all_channels[name] = []
            # 添加来源标记并去重
            self.all_channels[name] = list({f"{url} (来源:{source_name})" for url in urls})

    def match_template_channels(self):
        """匹配模板中的频道"""
        self.matched_channels = OrderedDict()
        for cat, names in self.template_channels.items():
            self.matched_channels[cat] = OrderedDict()
            for name in names:
                if name in self.all_channels:
                    self.matched_channels[cat][name] = self.all_channels[name]

    def sort_by_response(self, urls: List[str]) -> List[str]:
        """按响应时间排序URL
        :param urls: URL列表
        :return: 排序后的URL列表（升序）
        """
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            futures = [executor.submit(self.check_response_time, url) for url in urls]
            # 获取结果并按响应时间排序
            sorted_results = sorted([f.result() for f in futures], key=lambda x: x[1])
            return [url for url, _ in sorted_results]

    def generate_output(self):
        """生成最终输出文件（M3U/TXT）"""
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor, \
             open("output/live.m3u", "w", encoding="utf-8") as m3u_file, \
             open("output/live.txt", "w", encoding="utf-8") as txt_file:

            self.write_announcements(m3u_file, txt_file)
            written_urls = set()  # 全局去重已写入的URL

            for category in self.template_channels:
                txt_file.write(f"{category},#genre#\n")
                for channel_name, urls in self.matched_channels.get(category, {}).items():
                    # 提取原始URL（去除来源标记）
                    raw_urls = [url.split(" (来源:")[0] for url in urls]
                    # 去重并按响应时间排序
                    unique_urls = list({u for u in raw_urls if _is_valid_url(u)})
                    sorted_urls = self.sort_by_response(unique_urls)
                    
                    for idx, url in enumerate(sorted_urls, 1):
                        if url in written_urls:
                            continue
                        # 处理IP版本后缀
                        suffix = "$IPV6" if re.search(r"\[.*?\]", url) else "$IPV4"
                        processed_url = f"{url}{suffix}•线路{idx}" if idx > 1 else f"{url}{suffix}"
                        
                        self.write_channel(m3u_file, txt_file, category, channel_name, processed_url)
                        written_urls.add(url)

    def write_channel(self, m3u: object, txt: object, category: str, name: str, url: str):
        """写入单个频道条目
        :param m3u: M3U文件对象
        :param txt: TXT文件对象
        :param category: 频道分类
        :param name: 频道名称
        :param url: 处理后的URL
        """
        logo = f"{config.logo_base_url}{name}.png"
        m3u.write(f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}\n')
        m3u.write(f"{url}\n")
        txt.write(f"{name},{url}\n")

    def write_announcements(self, m3u: object, txt: object):
        """写入系统公告"""
        for ann in config.announcements:
            txt.write(f"{ann['channel']},#genre#\n")
            for entry in ann['entries']:
                m3u.write(f'#EXTINF:-1,{entry["name"]}\n{entry["url"]}\n')
                txt.write(f"{entry['name']},{entry['url']}\n")

# 主执行流程
if __name__ == "__main__":
    processor = ChannelProcessor()
    processor.process_template("channel_template.txt")
    
    # 异步获取所有数据源
    asyncio.run(processor.process_sources())
    processor.match_template_channels()
    
    # 生成输出文件
    processor.generate_output()
    logging.info("频道生成完成，已写入output目录")
