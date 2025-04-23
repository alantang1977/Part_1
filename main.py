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

# 日志配置（略，保持不变）

class ChannelManager:
    # 其他方法保持不变...

    def sort_channels_by_speed(self):
        """按响应速度排序（修正Future与URL关联）"""
        sorted_channels = OrderedDict()
        max_workers = multiprocessing.cpu_count() * 2 + 1  # 动态计算最佳线程数

        for name, urls in self.all_channels.items():
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 关键修复：保存URL和Future的对应关系
                future_urls = [(url, executor.submit(self._check_response_time, url)) for url in urls]
                results = []
                for current_url, future in future_urls:  # 使用current_url避免变量冲突
                    try:
                        results.append(future.result(timeout=10))  # 带超时的结果获取
                    except Exception as e:
                        logger.debug(f"URL {current_url} 检测超时: {str(e)}")
                        results.append((current_url, float('inf')))  # 关联正确的URL

                # 按响应时间排序并过滤无效URL
                sorted_urls = [
                    url for url, time in sorted(results, key=lambda x: x[1])
                    if time != float('inf')
                ]
                sorted_channels[name] = sorted_urls
        return sorted_channels

    # 其他方法保持不变...
