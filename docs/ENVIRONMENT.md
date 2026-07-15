# 环境配置

## 系统依赖

建议环境：

- macOS
- Python 3.10 或 3.11
- Node.js 22
- Corepack
- pnpm 10.15.1（已在前端 `package.json` 固定）
- FFmpeg / ffprobe
- `lsof`
- BaiduPCS-Go（自动发布从百度网盘下载资源时需要）

检查命令：

```bash
python3 --version
node --version
corepack --version
ffmpeg -version
ffprobe -version
lsof -v
```

## Highlight Service

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com
OPENAI_TEXT_MODEL=gpt-5.5
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_WIRE_API=responses
OPENAI_TRANSCRIBE_MODEL=whisper-1

TRANSCRIBE_PROVIDER=gemini
GEMINI_API_KEY=
GOOGLE_GEMINI_BASE_URL=
GEMINI_BASE_URL=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
GEMINI_TTS_VOICE=Kore
GEMINI_API_STYLE=native

VIDEO_INPUT_DIR=inputs
MAX_WORKERS=2
BAIDU_PCS_GO_PATH=/absolute/path/to/BaiduPCS-Go
BAIDU_PCS_REMOTE_ROOT=/短剧资源
BAIDU_PCS_TIMEOUT_SECONDS=60
```

说明：

- `OPENAI_BASE_URL` 可填写到域名或 `/v1`，图片客户端会自动规范化。
- 内容推广需要 OpenAI 文本模型和 `gpt-image-2`。
- 自动发布的片头片尾默认使用 `/v1/images/generations`；图片请求失败时会明确记录本地兜底模式。
- Gemini 用于音频转写、视觉策略或其他多模型分析。
- `.env` 含密钥，不要提交。

## Console Frontend

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
corepack enable
CI=true corepack pnpm install --frozen-lockfile
```

前端开发代理由启动脚本传入：

```dotenv
HIGHLIGHT_SERVICE_URL=http://127.0.0.1:8765
PUBLISH_SERVICE_URL=http://127.0.0.1:5409
HOST=127.0.0.1
PORT=8001
```

不要直接使用不匹配的全局 pnpm 重建 `node_modules`。项目固定使用 pnpm 10.15.1。

## Social Auto Upload

```bash
cd /Users/q/Desktop/work/highlight/apps/social-auto-upload
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[web]'
pip install playwright==1.52.0 schedule==1.2.2 xhs
playwright install chromium
```

常用可选变量：

```dotenv
SAU_PUBLISH_TASK_TIMEOUT_SECONDS=1800
SAU_XHS_CREATOR_BASE_URL=
DOUYIN_FORM_READY_TIMEOUT_MS=300000
DOUYIN_SCHEDULE_READY_TIMEOUT_MS=300000
DOUYIN_UPLOAD_COMPLETE_TIMEOUT_MS=300000
DOUYIN_PUBLISH_READY_TIMEOUT_MS=180000
DOUYIN_PUBLISH_SUBMIT_TIMEOUT_MS=300000
DOUYIN_DETECTION_GRACE_MS=15000
```

账号登录态位于 `apps/social-auto-upload/cookies/`。不要提交 Cookie、二维码、账号文件或平台运行日志。

## 启动与端口

后台重启：

```bash
cd /Users/q/Desktop/work/highlight
./restart-all.sh
```

覆盖端口或 worker 配置：

```bash
HIGHLIGHT_PORT=8766 \
SOCIAL_PORT=5410 \
CONSOLE_PORT=8002 \
WORKER_INTERVAL=3 \
WORKER_ID=local-worker-2 \
./restart-all.sh
```

服务日志：

```text
logs/highlight-service.log
logs/highlight-worker.log
logs/social-auto-upload.log
logs/highlight-console.log
```

## 健康检查

```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:5409/api/platforms
curl -I http://127.0.0.1:8001/
```

端口检查：

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
lsof -nP -iTCP:5409 -sTCP:LISTEN
lsof -nP -iTCP:8001 -sTCP:LISTEN
```

## 常见问题

### pnpm 在非 TTY 环境中拒绝清理 node_modules

使用项目固定版本重新安装：

```bash
cd apps/highlight-cutter/frontend
CI=true corepack pnpm install --frozen-lockfile
```

### GPT Image 2 返回 524

当前实现使用精简 prompt 和 `/images/generations`。如果兼容网关仍返回 524，应检查网关上游负载、Cloudflare 时限和模型映射；不要把本地 Pillow 兜底误认为 GPT Image 2 成功。

### 发布任务失败

先检查：

- 对应平台账号 Cookie 是否有效。
- Playwright Chromium 是否安装。
- 平台页面是否更新。
- 图片或视频本地路径是否存在。
- `logs/social-auto-upload.log` 中的 CLI 输出。

真实平台上传可能打开有头浏览器，并受登录验证、验证码、风控和平台页面变化影响。
