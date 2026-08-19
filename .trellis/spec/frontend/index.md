# Frontend Development Guidelines

本项目页面规范以 [项目页面开发规范](./project-guidelines.md) 为准，当前实现位于 `app/templates/`、`app/static/css/`、`app/static/js/` 和 `app/static/vendor/`。

| Guide | Status |
|---|---|
| [项目页面开发规范](./project-guidelines.md) | 已确定并按实现更新 |
| [Directory Structure](./directory-structure.md) | 待根据页面扩展 |
| [Component Guidelines](./component-guidelines.md) | 使用 Jinja 模板片段，不引入组件框架 |
| [Hook Guidelines](./hook-guidelines.md) | 不适用：使用原生事件监听 |
| [State Management](./state-management.md) | 使用页面筛选状态和 API 响应 |
| [Type Safety](./type-safety.md) | 不适用：不使用 TypeScript |
| [Quality Guidelines](./quality-guidelines.md) | 已通过本地浏览器和接口联调 |

前端统一使用本地 Lucide 图标和 ECharts，禁止使用 emoji 作为图标；看板、登录页和管理后台共享同一套深色数据画布、响应式布局与 reduced-motion 规则。
