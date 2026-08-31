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
- 城市地图、月度趋势、演唱会日历、票价分析、评论主题和艺人对比接口
- 基于城市、票价、售票状态、评论数和点赞数的规则推荐
- 浏览器本地收藏、两到三场演唱会对比、偏好设置和页面提醒
- 本地 Lucide 图标与 ECharts 图表，页面文案使用直白中文
- 管理后台的 CSV 导入预览、字段校验、重复检测、异常报告、任务详情和 CSV 导出
- 管理后台的演唱会基础信息最小化编辑

## 快速运行

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -m pip install -r requirements.txt
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe run.py
```

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

原始验证快照位于 `data/raw/`，清洗脚本输出到 `data/cleaned/`。除最初 9 来源快照（78 条）外，系统已扩充到十万级多来源数据：

- `musicbrainz_events.csv`：MusicBrainz（CC0 开放数据）演唱会事件，全量目标约 12.5 万条，后台低频采集续写中。
- `nyphil_concerts.csv`：Kaggle 纽约爱乐演出史（21607 场）。
- `showstart_concerts.csv`：秀动网演出列表爬虫采集（175 场真实国内演出）。
- `concerts_merged.csv`：`scripts/merge_datasets.py` 按（艺人、名称、场馆、日期）指纹合并去重后的统一快照；每条记录保留 `source_type`（公开数据集/爬虫采集）、`source_url` 和 `collected_at`，可随时复查「哪部分是爬取的、哪部分是公开数据集」。

数据扩充脚本：

```bash
# MusicBrainz 演唱会事件采集（公开数据集，低频限速，支持断电续传）
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/collect_musicbrainz.py
# Kaggle 纽约爱乐演出史下载转换（公开数据集）
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/convert_nyphil.py
# 秀动网演出列表爬虫（爬虫采集，低频）
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/collect_showstart.py
# 多来源合并去重
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/merge_datasets.py
```

清洗和分析：

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/clean_data.py
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/analyze_comments.py
```

采集脚本只处理允许访问的公开页面，不绕过登录、验证码、代理或访问限制；对 MusicBrainz 等限速来源使用低频请求与退避重试，对无 robots.txt 的秀动网同样控制访问频率。页面未提供票价时保留“待定”，日期范围按首场日期归档。系统启动时优先自动导入 `data/raw/concerts_merged.csv`（不存在时回退 `concerts.csv`）中尚未入库的记录；测试环境会关闭自动加载以保持测试数据稳定。演唱会日历为紧凑月历热力图（点按日期展开当日场次），并新增 `/api/analytics/sources` 数据来源统计接口。

## 测试

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -m pytest -q
```

当前测试覆盖健康检查、数据概览、城市筛选、六类扩展分析接口、管理员登录、CSV 预览、ORM 数据导入、任务详情、数据导出、场次编辑、分析任务、退出登录、本地公开快照规模检查和新数据库自动加载；最近一次结果为 `10 passed`。

## Trellis

本项目使用 Trellis 管理开发规范和任务记录。项目规范位于 `.trellis/spec/`，不改变毕业设计的技术范围。
