"""系统配置中心（所有外部依赖集中管理）"""
import os

# 基础配置
LOGO_BASE_URL = "https://gitee.com/IIII-9306/PAV/raw/master/logos/"  # 频道LOGO基础URL

# 数据源配置（支持多URL并发抓取）
SOURCE_URLS = [
    #"http://aktv.space/live.m3u",
    #"http://92.112.21.169:30000/mytv.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/hostemail/cdn/main/live/tv.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/alantang1977/JunTV/refs/heads/main/output/result.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u",
    "https://live.zbds.top/tv/iptv4.txt",
    "https://gitee.com/xxy002/zhiboyuan/raw/master/dsy",   
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/big-mouth-cn/tv/main/iptv-ok.m3u",
    "https://codeberg.org/alfredisme/mytvsources/raw/branch/main/mylist-ipv6.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/lalifeier/IPTV/main/m3u/IPTV.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/asdjkl6/tv/tv/.m3u/整套直播源/测试/整套直播源/l.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/asdjkl6/tv/tv/.m3u/整套直播源/测试/整套直播源/kk.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv6.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/yuanzl77/IPTV/main/live.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/YueChan/Live/refs/heads/main/APTV.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
    "https://live.zbds.top/tv/iptv6.txt",
    "http://xhztv.top/new.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/Guovin/TV/gd/output/result.txt",
    "http://home.jundie.top:81/Cat/tv/live.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/vbskycn/iptv/master/tv/hd.txt",
    "https://live.fanmingming.cn/tv/m3u/ipv6.m3u",
    "https://live.zhoujie218.top/tv/iptv6.txt",
    "https://cdn.jsdelivr.net/gh/YueChan/live@main/IPTV.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/cymz6/AutoIPTV-Hotel/main/lives.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/PizazzGY/TVBox_warehouse/main/live.txt",
    "https://fm1077.serv00.net/SmartTV.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/joevess/IPTV/main/home.m3u8",
    "https://tv.youdu.fan:666/live/",  
    "https://m3u.ibert.me/txt/o_cn.txt",
    "https://m3u.ibert.me/txt/j_iptv.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/xzw832/cmys/main/S_CCTV.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/xzw832/cmys/main/S_weishi.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/BurningC4/Chinese-IPTV/master/TV-IPV4.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/joevess/IPTV/main/m3u/iptv.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/Ftindy/IPTV-URL/main/IPV6.m3u",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    "https://iptv.b2og.com/txt/fmml_ipv6.txt",
    "http://xhztv.top/zbc.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output_simple.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/SPX372928/MyIPTV/master/黑龙江PLTV移动CDN版.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/qingwen07/awesome-iptv/main/tvbox_live_all.txt",
    "https://gh.tryxd.cn/https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.m3u",
    "https://live.zhoujie218.top/tv/iptv4.txt"
    # 保留原有其他源URL...
]

# 输出配置
OUTPUT_CONFIG = {
    "output_dir": "output",          # 输出目录
    "m3u_filename": "live.m3u",       # M3U文件名
    "txt_filename": "live.txt"        # TXT文件名
}

# 网络配置（统一管理超时和重试策略）
NETWORK_CONFIG = {
    "timeout": 10,           # 网络请求超时时间（秒）
    "max_retries": 3         # 最大重试次数
}

# 黑名单配置（正则表达式过滤无效URL）
URL_BLACKLIST = [
    r"epg\.pw/stream/",       # 示例：过滤包含特定路径的URL
    r"[2409:8087:1a01:df::7005]/ottrrs\.hl\.chinamobile\.com",  # 示例：过滤特定IPv6地址
    r"stream1\.freetv\.fun"   # 示例：过滤特定域名
]

# 系统公告配置（显示在文件顶部的特殊频道组）
ANNOUNCEMENTS = [
    {
        "channel": "系统公告",
        "entries": [
            {
                "name": "每日自动更新",
                "url": "https://codeberg.org/alantang/photo/raw/branch/main/ChatGPTImage.png",
                "logo": "https://gitee.com/IIII-9306/PAV/raw/master/logos/"
            }
        ]
    }
]

# EPG（电子节目指南）配置
EPG_URLS = [
    "https://epg.v1.mk/fy.xml",
    "http://epg.51zmt.top:8000/e.xml"
]
