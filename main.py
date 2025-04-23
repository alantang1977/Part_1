"""核心业务逻辑"""
import re
import requests
import logging
from datetime import datetime
from collections import OrderedDict
from config import SOURCE_CONFIG, OUTPUT_CONFIG, NETWORK_CONFIG, SYSTEM_ANNOUNCEMENTS
from utils.parser import Parser
from concurrent.futures import ThreadPoolExecutor

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", "a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

class ChannelManager:
    """频道管理核心类"""
    def __init__(self, template_path: str):
        self.template_path = template_path
        self.template_channels = Parser.parse_template(template_path)
        self.all_channels = OrderedDict()

    def fetch_and_merge_channels(self):
        """抓取并合并所有数据源频道"""
        for url in SOURCE_CONFIG["source_urls"]:
            try:
                content = self._fetch_url_content(url)
                source_type = self._detect_source_type(content)
                channels = Parser.parse_source(content, source_type)
                self._merge_channels(channels)
                logging.info(f"成功合并 {url} 频道数据")
            except Exception as e:
                logging.error(f"处理 {url} 时出错: {str(e)}")

    def _fetch_url_content(self, url: str) -> str:
        """获取URL内容"""
        response = requests.get(url, timeout=NETWORK_CONFIG["timeout"])
        response.raise_for_status()
        return response.text

    def _detect_source_type(self, content: str) -> str:
        """自动检测数据源类型"""
        return "m3u" if any(line.startswith("#EXTINF") for line in content.splitlines()[:15]) else "txt"

    def _merge_channels(self, source_channels: OrderedDict):
        """合并频道数据（去重处理）"""
        for name, urls in source_channels.items():
            self.all_channels[name] = list({u for u in self.all_channels.get(name, []) + urls})

    def sort_channels_by_speed(self) -> OrderedDict:
        """按响应速度排序频道URL"""
        sorted_channels = OrderedDict()
        with ThreadPoolExecutor(max_workers=NETWORK_CONFIG["max_workers"]) as executor:
            for name, urls in self.all_channels.items():
                results = executor.map(self._check_response_time, urls)
                sorted_urls = [url for url, _ in sorted(results, key=lambda x: x[1])]
                sorted_channels[name] = sorted_urls
        return sorted_channels

    @staticmethod
    def _check_response_time(url: str) -> tuple[str, float]:
        """检测URL响应时间（毫秒）"""
        try:
            start = datetime.now()
            requests.head(url, timeout=5, allow_redirects=True)
            return (url, (datetime.now() - start).microseconds / 1000)
        except Exception:
            return (url, float('inf'))

    def generate_output_files(self):
        """生成输出文件（M3U/TXT）"""
        os.makedirs(OUTPUT_CONFIG["output_dir"], exist_ok=True)
        with open(f"{OUTPUT_CONFIG['output_dir']}/live.m3u", "w", encoding="utf-8") as m3u, \
             open(f"{OUTPUT_CONFIG['output_dir']}/live.txt", "w", encoding="utf-8") as txt:
            self._write_announcements(m3u, txt)
            self._write_channel_data(m3u, txt)

    def _write_announcements(self, m3u, txt):
        """写入系统公告"""
        for group in SYSTEM_ANNOUNCEMENTS:
            txt.write(f"{group['channel']},#genre#\n")
            for entry in group["entries"]:
                self._write_channel_entry(m3u, txt, entry["name"], entry["url"], group["channel"], 0)

    def _write_channel_data(self, m3u, txt):
        """写入频道数据"""
        sorted_channels = self.sort_channels_by_speed()
        for category, channel_names in self.template_channels.items():
            txt.write(f"{category},#genre#\n")
            for idx, channel_name in enumerate(channel_names, 1):
                urls = sorted_channels.get(channel_name, [])
                for url_idx, url in enumerate(urls, 1):
                    self._write_channel_entry(m3u, txt, channel_name, url, category, url_idx)

    @staticmethod
    def _write_channel_entry(m3u, txt, name, url, category, idx):
        """写入单个频道条目"""
        logo = f"{OUTPUT_CONFIG['logo_base_url']}{name}.png"
        m3u_line = f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}\n{url}\n'
        txt_line = f"{name},{url}\n"
        m3u.write(m3u_line)
        txt.write(txt_line)

if __name__ == "__main__":
    manager = ChannelManager("demo.txt")
    manager.fetch_and_merge_channels()
    manager.generate_output_files()
    logging.info("频道列表更新完成，已生成标准M3U和TXT文件")
