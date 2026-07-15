# Highlight Cutter

本地运行的短视频高光剪辑工具。当前版本支持上传/扫描一组本地视频，并基于音频能量峰值自动导出候选高光片段；AI 模式会用 Gemini native 转写音频、GPT 分析台词、Gemini 复评关键帧。另有“剧情引流视频”模式，会按短剧推广逻辑拼出 hook、关系、冲突、反转/情绪点、悬念收尾，并自动生成开场标题卡和结尾悬念卡。

## 启动

当前目录只保留前端。FastAPI 后端已经拆到：

```text
/Users/q/Desktop/work/highlight/apps/highlight-service
```

先启动后端：

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

再启动前端：

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm install
pnpm dev
```

Umi 开发服务器默认会把 `/api` 代理到 `http://127.0.0.1:8765`。如需指向其它后端地址：

```bash
HIGHLIGHT_SERVICE_URL=http://127.0.0.1:8765 pnpm dev
```

## 使用

1. 在页面上传一组视频，或把视频放到后端服务的 `inputs/` 目录。
2. 上传完成后系统会自动扫描视频信息。
3. 选择“高光切片”或“剧情引流视频”。
4. 点击“生成高光视频”或“生成推广视频”。
5. 选择某个原视频，查看导出的高光片段。
6. 如需补剪，输入开始/结束时间后点击“导出片段”。

当前自动生成策略有两个入口：

- `本地快速`：用 FFmpeg 检测音频能量峰值，再向前后扩展成 30 秒左右的候选片段。
- `Codex CLI 复评`：先生成本地候选，再调用本机 `codex exec` 子进程做文本层复评。AI 模式会额外调用 Gemini 转写、GPT 台词分析和 Gemini 关键帧复评。

它能先跑通批量剪辑流程，但还不能完整理解剧情；剧情连贯性会在接入 OpenAI/Gemini、字幕和关键帧后增强。

推广视频接口：

```bash
curl -X POST 'http://127.0.0.1:8765/api/promos/generate?limit=3&windows_per_video=2'
```

参数说明：

- `limit`：本次最多分析多少个已上传视频，默认 3，最大 20。
- `windows_per_video`：每个视频抽取多少个剧情窗口，默认 2，最大 4。测试阶段建议先用 `limit=1&windows_per_video=1`。
- 输出视频：后端服务的 `outputs/promos/promo_latest.mp4`。
- 下载接口：`GET /api/promos/latest/download`。
- 推广视频会额外拼入约 1.2 秒开场蒙版文字和约 1.6 秒结尾蒙版文字；文案来自模型分类结果，报告中会显示 `opening` 和 `ending`。
- 每次推广生成会同时导出 4 个版本：`强钩子版`、`关系介绍版`、`反转版`、`悬念版`。对应文件在后端服务的 `outputs/promos/promo_hook.mp4`、`promo_relationship.mp4`、`promo_reversal.mp4`、`promo_cliffhanger.mp4`。

推广模式当前是 MVP：它会先用少量窗口验证链路和节奏，不会全量理解每一集。后续更适合改成后台任务队列，逐集缓存转写和关键帧结果，再做全局剧情编排。

时间格式支持：

```text
12.5
00:00:12.5
00:01:03
```

## 后续计划

- 后台任务队列和真正的后端取消任务。
- 转写/关键帧/模型分析缓存，避免重复消耗。
- 更完整的剧情引流编排：冷开场、人物身份、关系误会、核心冲突、反转、结尾 CTA。
- 批处理队列和失败重试。
- 百度云/云端存储来源扩展。
