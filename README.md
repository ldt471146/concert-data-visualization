# 演唱会数据分析与可视化系统

本仓库用于完成庞丽君（23001554）的本科毕业设计：**基于 Python 的演唱会数据分析与可视化系统设计与实现**。

## 交付内容

- [技术实施文档（Markdown）](docs/技术实施文档.md)
- [技术实施文档（Word）](docs/技术实施文档.docx)
- [设计系统规范](design-system/pulse-atlas/MASTER.md)
- [视觉参考记录](docs/视觉参考记录.md)

## 已实现模块

- 公开数据快照的 CSV 保存、清洗和去重
- Flask 应用与 SQLAlchemy ORM
- SQLite 默认运行，支持通过 `DATABASE_URL` 切换 MySQL
- 单管理员登录、退出和轻量管理后台
- 演唱会列表、评论文本、城市、票价和情绪统计
- jieba / SnowNLP 可选接入，缺少依赖时使用项目内置的轻量回退逻辑
- 城市、状态、时间和价格筛选
- **十四项分析**接口：城市地图、月度趋势、演唱会日历、票价分析、评论主题、艺人热度榜、数据来源、城市票价对比、互动热度榜、评论情感分布、场次星期分布、售票状态占比、评论平台构成、热门场馆；`/api/analytics/all` 批量返回全部十四项（一次查询上下文），前端仅发 `overview` + `analytics/all` 两个请求
- **Redis 缓存层**：概览/批量分析/推荐接口 TTL 缓存（分析 300 秒、概览与推荐 120 秒），命中 16 毫秒返回，Redis 不可用时自动降级
- 基于城市、票价、售票状态、评论数和点赞数的规则推荐
- **页面交互**：搜索条（艺人/场次/城市/场馆，回车出结果点击直达详情）、场次详情抽屉（票价明细 + 评论翻页 + 原页链接）、城市柱状图点击联动筛选、浏览器本地收藏、两到三场演唱会对比、偏好设置和页面提醒
- 本地 Lucide 图标与 ECharts 图表，页面文案使用直白中文
- 管理后台（五区 Tab）：数据总览仪表盘（统计卡片 + 近 7 日趋势 + 来源饼图）、演唱会管理（分页/筛选/行内编辑/单删/批量删除级联评论）、评论管理（分页/筛选/逐条删除）、CSV 导入导出（演唱会/评论）、系统运维（重建分析 / 清缓存）

## 快速运行

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -m pip install -r requirements.txt
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe run.py
```

> 性能优化依赖本机 Redis（默认 127.0.0.1:6379）：先 `redis-server` 启动 Redis，再运行系统。Redis 未启动时系统自动降级为无缓存模式，不影响功能。

打开 <http://127.0.0.1:5000> 查看数据看板。

本地管理员账号：`atlas`  
本地管理员密码：`pulse2025`

## MySQL 切换

默认使用项目 `instance/` 目录下的 SQLite 数据库，便于本地联调。准备好 MySQL 后设置连接串：

```bash
set DATABASE_URL=mysql+pymysql://用户名:密码@127.0.0.1:3306/concert_analysis?charset=utf8mb4
```

然后重新运行 `run.py`。生产环境应通过环境变量修改 `SECRET_KEY` 和管理员密码。

## 数据与脚本

数据为**多渠道真实演出 + 场次评论**，总量 **19 万+ 条**（场次 22618 + 评论 168576），全部来源可标注（论文可复查）：

- `damai_full_concerts.csv`：大麦网全部有效演出场次（演唱会/音乐会/音乐节等 6 分类，272 城市），`scripts/export_damai_full.py` 从本地大麦爬虫库导出。
- `damai_full_comments.csv`：大麦场次真实评论 118412 条（每条挂具体场次，与演出直接相关）。
- `comments_wyy_merged.csv`：网易云歌手热评 49060 条（按歌手关联艺人）。
- `comments_social_merged.csv`：B站"XX 演唱会"视频评论 1069 条（含观演现场讨论）。
- 前端支持**按分类筛选**，且**默认只展示演唱会分类**（1062 场）；选择「全部」可查看全库 22618 场。每条记录保留 `source_url` 与 `collected_at` 可复查。

数据脚本：

```bash
# 大麦爬虫库 → 全库有效场次 + 评论 CSV（本地 damai.db）
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/export_damai_full.py
# 三渠道(大麦/网易云/B站) → 系统数据库全量重建
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/import_all_channels.py
# B站"XX 演唱会"视频评论采集（wbi 签名公开接口，限速重试；--artists 指定艺人）
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/collect_social_comments.py --artists "薛之谦,周杰伦"
# 评论合并去重 → comments_social_merged.csv
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/merge_social_comments.py
# 评论关联演唱会场次 → comments_input.csv
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/build_comments_input.py
```

清洗和分析：

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/clean_data.py
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/analyze_comments.py
```

采集脚本只处理允许访问的公开页面，不绕过登录、验证码、代理或访问限制；B站评论使用公开 API + wbi 签名（无需登录），单次请求间隔 ≥1 秒、风控自动退避，每条评论保留来源平台与链接。系统启动时自动导入 `concerts_merged.csv`（大麦演唱会）与 `comments_input.csv`（现场评论）中尚未入库的记录，导入幂等去重；测试环境关闭自动加载以保持测试数据稳定。演唱会日历为紧凑月历热力图（点按日期展开当日场次）；`/api/analytics/platforms` 按评论区来源 URL 域名识别大麦/网易云/B站平台构成，使用全量 SQL 聚合不受采样上限影响。

## 测试

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -m pytest -q
```

当前测试覆盖健康检查、数据概览、城市筛选、十四项分析接口（含批量接口）、场次详情与评论分页、关键字搜索、艺人趋势、管理员登录与鉴权、管理后台统计/分页列表、评论导出、CSV 预览、ORM 数据导入、任务详情、数据导出、场次编辑、分析任务、本地公开快照规模检查和新数据库自动加载；最近一次结果为 `21 passed`，含十万级数据规模断言（演唱会记录 + 评论记录合计 ≥ 10 万）。

## Trellis

本项目使用 Trellis 管理开发规范和任务记录。项目规范位于 `.trellis/spec/`，不改变毕业设计的技术范围。
