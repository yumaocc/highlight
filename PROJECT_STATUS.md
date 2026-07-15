# Highlight Project Status

## 当前定位

`highlight` 是已经打通的本地短剧内容生产与分发控制台，不再是多个孤立工具的规划稿。

当前服务边界：

- `highlight-service`：资源查询、下载、扫描、视频处理、AI 内容、GPT Image 2 图片和自动发布任务编排。
- `highlight-cutter/frontend`：统一 Ant Design 控制台。
- `social-auto-upload`：账号登录、视频发布、图文发布和平台 CLI/uploader。

## 已投入使用的流程

1. 自动发布：短剧名称 → 资源匹配 → 下载 → 扫描 → 合成 → 发布。
2. 失败恢复：任务和原始配置落入 SQLite，按条目复用已完成阶段。
3. 内容推广：描述 → GPT 推广文案 → GPT Image 2 宣传图 → 账号选择 → 图文发布。
4. 手动发布：本地视频 → 平台与账号 → 发布任务。
5. 账号管理：平台登录、Cookie 状态与账号删除。

## 当前菜单

- 自动发布
- 已发布短剧
- 内容推广
- 发布中心
- 平台账号
- 系统设置

旧的“批量工作流”菜单、页面、前端 service、模板 API、任务执行代码和初始化逻辑已经移除。通用 pipeline 引擎仍服务于手动剪辑页和自动发布的可选剪辑模板。

## 运行状态

- Console：`127.0.0.1:8001`
- Highlight API：`127.0.0.1:8765`
- Social upload API：`127.0.0.1:5409`
- Pipeline worker：由 `restart-all.sh` 独立启动

安装与配置见 [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)。

## 已知风险

- 平台上传依赖 Cookie、验证码、风控和页面结构，必须保留可读日志与失败重试。
- 第三方 OpenAI 兼容网关可能对长图片请求返回 524。
- 本地文件路径交接要求剪辑服务和发布服务运行在同一台机器。
- 自动发布任务已经持久化，但发布服务自身的任务列表仍主要保存在进程内存。

## 验证基线

- 前端：`corepack pnpm build`
- Highlight 后端：`python -m py_compile app/*.py`
- 自动发布：`python -m unittest tests.test_auto_publish tests.test_auto_compose -v`
- 图文发布：`python -m unittest tests.test_publish_note_api -v`
