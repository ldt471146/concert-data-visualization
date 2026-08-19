# Backend Development Guidelines

本项目后端规范以 [项目后端开发规范](./project-guidelines.md) 为准，当前实现位于仓库根目录的 `app/`、`config.py`、`run.py` 和 `scripts/`。

| Guide | Status |
|---|---|
| [项目后端开发规范](./project-guidelines.md) | 已确定并按实现更新 |
| [Directory Structure](./directory-structure.md) | 待根据后续模块扩展 |
| [Database Guidelines](./database-guidelines.md) | 待根据真实表结构补充 |
| [Error Handling](./error-handling.md) | 待根据异常日志补充 |
| [Quality Guidelines](./quality-guidelines.md) | 待根据测试覆盖补充 |
| [Logging Guidelines](./logging-guidelines.md) | 使用 `JobRun` 运行记录 |

后端已具备 SQLite 默认联调、MySQL 连接串切换、SQLAlchemy ORM、Flask-Login 管理员会话、CSV 导入、评论分析和规则推荐接口。
