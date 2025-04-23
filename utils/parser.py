"""
数据源解析工具模块
支持解析 M3U 和 TXT 格式的直播源文件
"""

def parse_source_content(content, source_type):
    """
    解析数据源内容（M3U/TXT）
    :param content: 数据源文件内容（字符串）
    :param source_type: 数据源类型（"m3u" 或 "txt"）
    :return: 解析后的频道字典 {频道名: [线路列表]}
    """
    channels = {}
    if source_type == "m3u":
        return _parse_m3u(content)
    elif source_type == "txt":
        return _parse_txt(content)
    return channels

def _parse_txt(content):
    """解析 TXT 格式的直播源（每行格式：频道名,URL$IPV6•线路XX）"""
    channels = {}
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or "," not in line:
            continue
        # 分割频道名和 URL 部分
        channel_name, url_part = line.split(",", 1)
        # 提取 URL 和线路号（处理 $IPV6•线路XX 后缀）
        url, line_info = url_part.split("$IPV6•", 1)
        line_number = line_info.split("线路")[-1].strip()  # 提取线路号（如 "22"）
        # 存储到频道字典
        if channel_name not in channels:
            channels[channel_name] = []
        channels[channel_name].append({
            "url": url,
            "line_number": line_number
        })
    return channels

def _parse_m3u(content):
    """解析 M3U 格式的直播源（示例框架，需根据实际格式扩展）"""
    channels = {}
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            # 提取频道名（示例逻辑，实际需解析 EXTINF 标签）
            channel_name = line.split(",")[-1] if "," in line else "未知频道"
        elif line.startswith("http"):
            # 假设每行 URL 对应上一个 EXTINF 的频道
            if "channel_name" in locals():
                if channel_name not in channels:
                    channels[channel_name] = []
                channels[channel_name].append({"url": line})
    return channels

# 示例用法
if __name__ == "__main__":
    # 读取 TXT 示例内容（模拟 live_ipv6.txt 格式）
    txt_content = """
    江西卫视,http://[2409:8087:4c0a:22:1::11]:6410/...$IPV6•线路22
    安徽卫视,http://[2409:8087:5e01:34::38]:6610/...$IPV6•线路23
    """
    parsed = parse_source_content(txt_content, "txt")
    print(f"解析结果: {parsed}")
