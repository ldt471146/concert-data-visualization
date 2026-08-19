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

原始验证快照位于 `data/raw/`，清洗脚本输出到 `data/cleaned/`。当前合并后的演唱会快照包含 `78` 条记录、`57` 位艺人和 `12` 个城市；新增批次和来源核验记录分别位于 `data/raw/concerts_public.csv`、`data/raw/public_sources.csv`。

重新核验公开来源并合并新批次：

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/collect_public_snapshot.py
```

清洗和分析：

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/clean_data.py
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/analyze_comments.py
```

采集脚本只处理允许访问的公开页面，不绕过登录、验证码、代理或访问限制。页面未提供票价时保留“待定”，日期范围按首场日期归档，并在名称中保留多场说明。系统启动时会自动把 `data/raw/concerts.csv` 中尚未入库的演唱会记录导入本地数据库；测试环境会关闭自动加载以保持测试数据稳定。


## 测试

```bash
C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -m pytest -q
```

当前测试覆盖健康检查、数据概览、城市筛选、六类扩展分析接口、管理员登录、CSV 预览、ORM 数据导入、任务详情、数据导出、场次编辑、分析任务、退出登录、本地公开快照规模检查和新数据库自动加载；最近一次结果为 `10 passed`。

## Trellis

本项目使用 Trellis 管理开发规范和任务记录。项目规范位于 `.trellis/spec/`，不改变毕业设计的技术范围。
