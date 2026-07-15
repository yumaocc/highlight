{
  "type": "single-screen SaaS product UI mockup",
  "goal": "Redesign a local short drama highlight editing dashboard so the primary focus is uploading videos, model output content, and generated assets/products. The page should feel like a professional productivity tool, not a marketing page.",
  "viewport": {
    "width": "desktop 1440px app viewport",
    "aspect_ratio": "16:9 desktop screenshot",
    "browser_chrome": "none"
  },
  "product_context": {
    "name": "Highlight Console",
    "language": "Chinese UI labels",
    "audience": "content operators who batch upload short drama episodes, run AI clipping, inspect model reasoning, and download generated clips"
  },
  "layout": {
    "shell": "fixed left navigation sidebar, content canvas on light gray background",
    "sidebar": {
      "width": "260px",
      "content": ["brand mark HC", "menu items: 短剧剪辑, 发布中心, 平台账号", "small bottom note only"],
      "avoid": "no runtime status card, no large diagnostic panel"
    },
    "main_content": {
      "header": "compact page title 批量高光剪辑 with one-line subtitle and small status pill on the right",
      "primary_area": "one dominant workbench card occupying the first viewport",
      "primary_card_layout": "left 65% large upload dropzone, right 35% generation settings and compact task progress stacked",
      "secondary_area": "two-column output grid below primary card: left 模型输出, right 产物",
      "tertiary_area": "uploaded source list as a compact table below or inside the upload card footer, visually secondary"
    },
    "priority_order": [
      "1. Upload video dropzone must be visually dominant",
      "2. Generated assets/products must be easy to scan",
      "3. Model output content should be readable and timeline-like",
      "4. Task controls and debug actions should be compact secondary controls"
    ]
  },
  "components": {
    "upload_dropzone": {
      "size": "large, calm, central",
      "text": ["上传短剧素材", "拖入一组视频或点击选择", "支持 mp4 / mov / mkv / webm / avi"],
      "visual": "large upload icon, subtle dashed border, no clutter"
    },
    "generation_panel": {
      "fields": ["生成类型 segmented control: 高光切片 / 剧情引流", "分析引擎 select", "primary button: 开始生成"],
      "progress": "thin progress bar with elapsed time and current step, small stop button"
    },
    "model_output": {
      "title": "模型输出",
      "content": "timeline cards for 本地峰值, GPT 台词分析, Gemini 画面复评, Codex 复核",
      "empty_state": "quiet text: 生成后显示模型判断和关键片段理由"
    },
    "assets_panel": {
      "title": "产物",
      "content": "cards for generated videos with thumbnail placeholder, duration, variant tag, download and publish actions",
      "manual_clip": "small collapsed row or inline form named 手动补剪, not a separate large card"
    },
    "source_table": {
      "title": "素材列表",
      "style": "compact, secondary, no huge empty area"
    }
  },
  "style": {
    "design_language": "Ant Design compatible, quiet operational dashboard, compact but polished",
    "colors": "light neutral background, white panels, charcoal text, teal primary accent, subtle slate borders, restrained warning red only for errors",
    "spacing": "clear hierarchy, 16-24px gutters, no nested cards inside cards",
    "cards": "8px radius max, thin borders, minimal shadows",
    "typography": "Inter / system sans, no oversized hero typography, headings fit tool surfaces",
    "icons": "simple line icons in buttons and section headers"
  },
  "constraints": {
    "must_keep": [
      "upload video area is the strongest first visual signal",
      "model output and generated assets are visible without scrolling too far",
      "debug controls do not dominate",
      "uploaded video table does not occupy most of the screen when empty",
      "all Chinese UI text is readable and realistic"
    ],
    "avoid": [
      "landing page hero styling",
      "too many equally weighted cards",
      "large empty tables",
      "runtime status card in sidebar",
      "decorative gradient orbs or bokeh backgrounds",
      "purple-heavy theme"
    ]
  }
}
