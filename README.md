# Highlight

本地短剧剪辑和多平台发布工作台。

## 一键启动

```bash
cd /Users/q/Desktop/work/highlight
./start-all.sh
```

启动后：

- Console web: `http://127.0.0.1:8001`
- Highlight API: `http://127.0.0.1:8765`
- Social upload API: `http://127.0.0.1:5409`

日志会写到：

```text
logs/highlight-service.log
logs/social-auto-upload.log
logs/highlight-console.log
```

按 `Ctrl+C` 会停止脚本启动的三个进程。

## 端口覆盖

```bash
HIGHLIGHT_PORT=8766 SOCIAL_PORT=5410 CONSOLE_PORT=8002 ./start-all.sh
```

## 当前子项目

- `apps/highlight-service`：短剧剪辑 FastAPI 后端。
- `apps/highlight-cutter/frontend`：统一前端工作台。
- `apps/social-auto-upload`：多平台发布后端和底层上传能力。
# highlight
