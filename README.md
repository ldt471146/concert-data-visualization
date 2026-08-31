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
- 城市地图、月度趋势、演唱会日历、票价分析、评论主题、艺人热度榜、数据来源、城市票价对比和互动热度榜（九项分析）接口
- **Redis 缓存层**：10 个分析/推荐接口 TTL 缓存（分析 300 秒、概览与推荐 120 秒），命中后 64-102 毫秒返回，Redis 不可用时自动降级
- 基于城市、票价、售票状态、评论数和点赞数的规则推荐
- 浏览器本地收藏、两到三场演唱会对比、偏好设置和页面提醒
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

数据主体为**国内真实演唱会 + 现场观演评论**，全部来源可标注（论文可复查）：

- `damai_concerts.csv` / `concerts_merged.csv`：大麦网演唱会分类 846 场真实演唱会（307 位艺人 / 140 城市），`scripts/export_damai.py` 从本地大麦爬虫库导出。
- `comments_social_merged.csv` / `comments_input.csv`：B站演唱会视频评论（wbi 公开接口，无需登录，1088 条）+ 大麦场次评论（45 条），`scripts/collect_social_comments.py` 采集、`scripts/merge_social_comments.py` 合并。
- 每条评论标注 `source_platform`（bilibili/damai）与 `source_url`；每条演唱会标注 `source_type` 与来源页面。

数据脚本：

```bash
# 大麦爬虫库 → 系统演唱会场次 CSV（本地 damai.db）
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/export_damai.py
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

采集脚本只处理允许访问的公开页面，不绕过登录、验证码、代理或访问限制；B站评论使用公开 API + wbi 签名（无需登录），单次请求间隔 ≥1 秒、风控自动退避，每条评论保留来源平台与链接。系统启动时自动导入 `concerts_merged.csv`（大麦演唱会）与 `comments_input.csv`（现场评论）中尚未入库的记录，导入幂等去重；测试环境关闭自动加载以保持测试数据稳定。演唱会日历为紧凑月历热力图（点按日期展开当日场次），并包含 `/api/analytics/sources` 数据来源统计接口。

## 测试

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -m pytest -q
```

当前测试覆盖健康检查、数据概览、城市筛选、扩展分析接口、管理员登录与鉴权、管理后台统计/分页列表、评论导出、CSV 预览、ORM 数据导入、任务详情、数据导出、场次编辑、分析任务、本地公开快照规模检查和新数据库自动加载；最近一次结果为 `15 passed`，含十万级数据规模断言（演唱会记录 + 评论记录合计 ≥ 10 万）。

## Trellis

本项目使用 Trellis 管理开发规范和任务记录。项目规范位于 `.trellis/spec/`，不改变毕业设计的技术范围。
