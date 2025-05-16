<div align="center">
  <img src="https://raw.githubusercontent.com/alantang1977/X/main/Pictures/TangImage240.png" alt="logo"/>
  <h1 align="center">SuperA</h1>
</div>

<div align="center">该仓库 SuperA 是一个用于整理和生成网络直播频道列表的项目，主要包含频道数据解析、匹配及自动化更新功能。</div>
<br>
<p align="center">
  <a href="https://github.com/alantang1977/SuperA/releases">
    <img src="https://img.shields.io/github/v/release/alantang1977/SuperA" />
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-%20%3D%203.13-47c219" />
  </a>
  <a href="https://github.com/alantang1977/SuperA/releases">
    <img src="https://img.shields.io/github/downloads/alantang1977/SuperA/total" />
  </a>
  <a href="https://github.com/alantang1977/SuperA">
    <img src="https://img.shields.io/github/stars/alantang1977/SuperA" />
  </a>
  <a href="https://github.com/alantang1977/SuperA/fork">
    <img src="https://img.shields.io/github/forks/alantang1977/SuperA" />
  </a>
</p>


# 以下是仓库的详细介绍：
## 核心功能
频道数据管理 

模板定义：demo.txt 中定义了频道分类（如 “央视频道”“卫视频道”“港・澳・台” 等），每个分类下列出具体频道名称（如 CCTV-1、东方卫视、翡翠台等）。

数据源：live_ipv6.txt 包含各频道的直播流 URL（基于 IPv6 地址），每个频道可能有多个备用线路（如 “线路 2”“线路 3”），用于提高可用性。
解析与匹配
utils/parser.py 提供解析工具，支持 M3U 和 TXT 格式，过滤黑名单 URL 并验证 IP 有效性。

main.py 中的 match_channels 函数负责将模板频道与数据源中的频道匹配，确保模板中的每个频道对应数据源中的有效 URL。
自动化更新
通过 .github/workflows/main.yml 配置定时任务（每 2 天凌晨 00:55），自动执行以下流程：

安装依赖（如requests）。
运行主脚本生成最新的 live.m3u 和 live.txt。

下载多个 EPG 文件（电子节目指南），用于显示节目信息。
提交更新到仓库，保持数据实时性。
输出格式
M3U 播放列表：output/live.m3u 可直接用于支持 M3U 格式的播放器（如 VLC、IPTV 客户端），包含频道名称和直播流 URL。

文本列表：output/live.txt 提供清晰的频道列表，方便人工查看或二次处理。
技术细节
IPv6 支持：数据源 URL 使用 IPv6 地址（如 [2409:8087:5e01:34::20]），适用于 IPv6 网络环境。

去重与过滤：通过 _is_blacklisted 函数排除无效或被禁止的 URL，确保链接可用性。
分类匹配：按模板中的分类（如 “卫视频道”“港・澳・台”）组织频道，便于用户按类别浏览。

使用场景
IPTV 服务：生成可用于 IPTV 客户端的播放列表，支持多线路切换。
直播聚合：整理多个来源的直播流，按分类展示，方便用户快速找到目标频道。
自动化维护：通过定时任务自动更新链接和 EPG，减少人工维护成本。

注意事项
版权问题：确保数据源中的直播流链接具有合法授权，避免侵权风险。
链接有效性：定时任务可能因服务器变更导致链接失效，需定期检查数据源或扩展错误处理逻辑。
网络环境：依赖 IPv6 网络访问直播流，确保用户设备或服务器支持 IPv6。
通过以上功能，该仓库实现了从数据解析、匹配到自动化更新的完整流程，适用于需要高效管理和分发网络直播频道的场景
