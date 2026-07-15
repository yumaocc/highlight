# Highlight

`highlight` 是一个面向短剧团队的本地内容生产与分发工作台。它把素材获取、视频合成、AI 文案、GPT Image 2 宣传图、多账号管理和多平台发布串成统一操作流程，同时保持剪辑服务与发布服务相互独立。

## 当前能力

- **自动发布**：按短剧名称查找资源、下载剧集、裁剪首尾、生成片头片尾并提交平台发布。
- **失败重试**：自动发布条目会保存阶段检查点，失败后可从资源、下载、扫描、成片或发布阶段继续。
- **内容推广**：输入一段描述，由 GPT 完善标题、正文、话题和推广策略，再由 GPT Image 2 生成宣传图。
- **图文发布**：将推广内容发布到已登录的抖音、快手或小红书账号。
- **发布中心**：选择本地视频、平台账号和发布参数，创建视频发布任务。
- **平台账号**：管理不同平台的登录账号和 Cookie 状态。
- **已发布记录**：查看自动发布过的短剧与关联任务。

## 架构

```text
apps/highlight-cutter/frontend   Umi Max + React + Ant Design 控制台
             │ /api                         │ /publish-api
             ▼                              ▼
apps/highlight-service          apps/social-auto-upload
FastAPI 剪辑、AI、资源与任务      Flask API + CLI/uploader 平台适配
```

服务通过 HTTP API 交互。前端不会直接导入后端代码，`highlight-service` 也不会直接依赖上传器内部模块。

## 快速启动

首次运行先完成 [环境配置](docs/ENVIRONMENT.md)。之后在项目根目录执行：

```bash
./restart-all.sh
```

访问地址：

- 控制台：http://127.0.0.1:8001
- Highlight API：http://127.0.0.1:8765
- API 文档：http://127.0.0.1:8765/docs
- Social upload API：http://127.0.0.1:5409

`restart-all.sh` 会停止旧进程、启动三个服务和 pipeline worker，然后返回终端。PID 位于 `.run/`，日志位于 `logs/`。

需要前台运行并在 `Ctrl+C` 时停止所有服务，可执行：

```bash
./start-all.sh
```

## 控制台菜单

- 自动发布
- 已发布短剧
- 内容推广
- 发布中心
- 平台账号
- 系统设置

## 目录

```text
apps/highlight-service          FastAPI 后端与 SQLite 数据
apps/highlight-cutter/frontend  控制台前端
apps/social-auto-upload         平台登录、CLI 与 uploader
docs/                           架构、环境和实现记录
logs/                           本地服务日志，不提交
.run/                           本地 PID 文件，不提交
```

## 验证

```bash
cd apps/highlight-service
.venv/bin/python -m py_compile app/*.py
.venv/bin/python -m unittest tests.test_auto_publish tests.test_auto_compose -v

cd ../highlight-cutter/frontend
corepack pnpm build

cd ../../social-auto-upload
.venv/bin/python -m unittest tests.test_publish_note_api -v
```

真实平台发布依赖有效账号、浏览器环境和平台页面状态，自动测试不会执行真实发布。
