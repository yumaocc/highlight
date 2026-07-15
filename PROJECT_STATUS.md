# Highlight Project Status

## 项目定位

`highlight` 现在是一个用于短剧内容生产和分发的本地工作台。目标不是把剪辑、发布、账号管理全部写进一个大项目里，而是保留多个独立服务，通过统一前端和稳定 API 把它们串起来。

核心链路：

1. 短剧素材进入剪辑服务。
2. 剪辑服务生成高光片段或剧情引流视频。
3. 发布服务管理平台账号、登录态和上传任务。
4. 统一前端按菜单调用不同后端服务，完成剪辑、预览、发布和任务查看。

## 当前目录状态

```text
highlight/
  apps/
    highlight-service/      # 独立 FastAPI 后端：短剧剪辑和推广视频生成
    highlight-cutter/       # 剪辑前端：Umi/Ant Design 页面
    social-auto-upload/     # 多平台自动发布能力：CLI、uploader、历史 Web 代码
```

## 已完成

### highlight-service

`highlight-service` 已经从原来的 `highlight-cutter` 一体项目里拆出，变成独立 FastAPI 服务。

当前能力：

- 上传和扫描本地视频。
- 基于 FFmpeg 音频能量峰值生成候选高光片段。
- 支持 Codex CLI 复评候选片段。
- 支持 Gemini 转写、GPT 台词分析、Gemini 关键帧复评。
- 支持剧情引流视频生成，包含 hook、关系、冲突、反转/情绪点、悬念收尾等版本。
- 后端运行数据独立存放在自己的 `inputs/`、`outputs/`、`work/`、`data/` 下。
- 已去掉 FastAPI 托管前端静态文件的耦合。

启动入口：

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

### highlight-cutter

`highlight-cutter` 当前只保留剪辑前端。

当前状态：

- 前端位于 `apps/highlight-cutter/frontend`。
- `/api` 请求通过 Umi proxy 转发到 `highlight-service`。
- 可通过 `HIGHLIGHT_SERVICE_URL` 指向不同后端地址。
- 生产构建产物输出到前端自己的 `dist/`，不再输出到后端 `static/`。

启动入口：

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm dev
```

### social-auto-upload

`social-auto-upload` 是当前发布能力的基础项目。

当前能力重点：

- 已有多平台 uploader 和 CLI 主线。
- 支持抖音、小红书、快手、Bilibili、YouTube 等平台的登录检查和上传能力，具体成熟度按平台不同有差异。
- 多账号以 `account_name` 为核心概念，一个账号名对应一份登录态或账号文件。
- 当前主线偏 CLI、Skill、无头或半自动浏览器自动化。
- 历史 Web 代码仍存在，但不是当前主线，后续不建议直接作为最终统一前端使用。

## 当前问题

1. 还没有统一前端工作台

   现在剪辑前端和发布工具仍然是两个项目。用户想要的最终形态应该是一个独立前端，通过菜单进入不同功能模块，而不是分别启动和操作多个页面或 CLI。

2. 发布服务还没有被整理成稳定后端 API

   `social-auto-upload` 的核心能力已经有，但更多是 CLI/uploader 形态。要接入统一前端，需要包装一层独立后端服务，提供账号、平台、登录、任务、上传、状态查询等 HTTP API。

3. 任务系统还不统一

   剪辑生成、AI 分析、上传发布都是长耗时任务。目前需要统一任务模型，例如 `pending/running/succeeded/failed/canceled`，并支持进度、日志、失败原因和重试。

4. 存储和文件交接还比较原始

   剪辑服务输出的视频文件需要能被发布服务消费。短期可以用本地路径约定，后续需要抽象成素材库或文件资产表。

5. 多账号管理需要产品化

   `social-auto-upload` 已有 `account_name` 概念，但统一前端里还需要账号列表、登录状态、重新登录、平台绑定、账号备注、默认发布配置等能力。

## 规划目标

### 总体目标

把 `highlight` 做成一个“短剧剪辑 + 多平台分发”的本地运营控制台。

架构目标：

- 服务之间独立部署、独立依赖、独立运行。
- 前端只通过 HTTP API 调用后端，不直接引用后端代码。
- 剪辑服务不关心发布平台。
- 发布服务不关心视频如何生成，只接收待发布素材和发布参数。
- 后续可以增加新的服务，例如素材库、任务调度、账号风控、云存储同步。

### 短剧项目与管道流程设计

新的生产流程以“短剧项目”为核心，不再把生成能力设计成孤立的视频按钮。
项目下挂载多个原始素材，每个素材可以进入不同的管道模板，管道的每一步都会记录中间产物，最终生成可预览、下载、单独发布或项目级批量发布的资产。

详细设计见：[docs/PIPELINE_DESIGN.md](docs/PIPELINE_DESIGN.md)。
结合当前代码状态的开发计划见：[docs/PIPELINE_DEVELOPMENT_PLAN.md](docs/PIPELINE_DEVELOPMENT_PLAN.md)。
逐步实现记录见：[docs/PIPELINE_IMPLEMENTATION_LOG.md](docs/PIPELINE_IMPLEMENTATION_LOG.md)。
任务完成状态见：[docs/PIPELINE_TASK_TRACKER.md](docs/PIPELINE_TASK_TRACKER.md)。

## 推荐目标架构

```text
apps/
  console-web/              # 新统一前端：菜单聚合所有功能
  highlight-service/        # 剪辑后端
  publish-service/          # 基于 social-auto-upload 包装出的发布后端
  social-auto-upload/       # 保留为发布底层能力库或上游代码
```

服务边界：

- `console-web`：负责 UI、菜单、任务看板、账号管理、素材选择、调用各服务 API。
- `highlight-service`：负责视频扫描、剪辑、AI 分析、推广视频生成。
- `publish-service`：负责平台账号、登录态、上传发布、发布状态、平台适配。
- `social-auto-upload`：短期作为 `publish-service` 的内部依赖或代码来源，长期可逐步沉淀为稳定 library。

## 阶段计划

### Phase 1：整理现有服务边界

目标：先把当前项目边界稳定下来。

- 保持 `highlight-service` 独立运行。
- 保持 `highlight-cutter` 前端只调用 API。
- 不再把前端构建产物塞回后端目录。
- 为根目录补充统一启动说明。
- 明确运行端口约定：
  - `highlight-service`: `8765`
  - `publish-service`: 待定，建议 `8770`
  - `console-web`: 待定，建议 `8000` 或 Vite 默认端口

### Phase 2：抽 publish-service

目标：把 `social-auto-upload` 包装成独立后端服务，而不是直接让统一前端调用 CLI。

建议优先 API：

- `GET /api/platforms`：平台列表和能力说明。
- `GET /api/accounts`：账号列表。
- `POST /api/accounts/{platform}/login`：启动登录流程。
- `GET /api/accounts/{platform}/{account}/status`：检查登录态。
- `POST /api/publish/video`：创建视频发布任务。
- `GET /api/tasks`：任务列表。
- `GET /api/tasks/{task_id}`：任务详情、进度、日志和失败原因。

短期实现可以内部调用现有 `sau` CLI 或 uploader 函数；长期再整理成更干净的 Python service layer。

### Phase 3：新增统一前端 console-web

目标：不要继续在 `highlight-cutter` 上硬塞所有功能，而是创建新的统一前端。

建议菜单：

- 素材库
- 短剧剪辑
- 剧情引流视频
- 发布任务
- 平台账号
- 系统设置

技术建议：

- React + Ant Design。
- 如果继续沿用现有前端，可从 `highlight-cutter/frontend` 迁移页面和 API 调用。
- 前端通过环境变量配置服务地址：
  - `HIGHLIGHT_SERVICE_URL`
  - `PUBLISH_SERVICE_URL`

### Phase 4：打通剪辑到发布

目标：完成核心业务闭环。

最小闭环：

1. 在剪辑服务生成视频。
2. 前端展示生成结果。
3. 用户选择一个或多个视频。
4. 用户选择平台账号和发布参数。
5. 前端调用发布服务创建上传任务。
6. 前端展示发布进度和结果。

短期文件交接方式：

- 前端把 `highlight-service` 返回的本地文件路径传给 `publish-service`。
- 两个服务运行在同一台机器时，发布服务直接读取该路径。

后续更稳的方式：

- 引入统一资产表。
- 每个生成文件有 `asset_id`、文件路径、来源服务、标题建议、封面、时长、分辨率、创建时间。
- 发布服务接收 `asset_id`，再通过约定路径或文件服务读取素材。

### Phase 5：任务、日志和可靠性

目标：把长耗时流程从“点击后等待”改成可恢复、可追踪的任务。

重点：

- 后台任务队列。
- 任务取消。
- 失败重试。
- 任务日志落库。
- 模型分析缓存。
- 上传失败原因结构化。
- 浏览器自动化状态截图或录屏留痕。

## 近期优先级

建议接下来按这个顺序做：

1. 新建根目录 README，写清楚三个子项目如何启动。
2. 抽 `publish-service`，先做账号列表、登录检查、单平台上传的最小 API。
3. 新建 `console-web`，先做菜单框架和服务健康检查页。
4. 把现有剪辑页面迁入 `console-web`。
5. 做发布账号管理页。
6. 做“剪辑结果 -> 发布任务”的打通页面。
7. 再考虑更复杂的任务队列、素材库和多平台批量发布。

## 非目标

短期不建议做：

- 不要把两个后端合并成一个大服务。
- 不要把 `social-auto-upload` 的历史 Web 端直接当最终前端。
- 不要一开始就做复杂的云端部署和多人权限。
- 不要先追求全平台完美，应该先跑通 1-2 个主要平台的稳定闭环。
- 不要让剪辑服务直接依赖发布服务的内部代码。

## 当前结论

项目方向是可行的，而且现在已经完成了第一步关键拆分：剪辑后端已经独立出来。

下一步最关键的不是继续堆功能，而是把 `social-auto-upload` 包装成稳定的 `publish-service`，再新建一个统一前端作为真正的操作入口。只要这两步完成，整个项目就会从“两个工具放在一起”变成“一个可扩展的内容生产和分发工作台”。
