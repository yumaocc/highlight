{
  "type": "SaaS console UI redesign mockup",
  "goal": "Design a practical homepage dashboard for a short-drama video production console. The page must make upload, AI generation, preview, and publish easy to operate in one scan.",
  "product_context": {
    "name": "Highlight",
    "audience": "short-drama operators who batch upload episode materials, generate highlight or promo cuts, review outputs, and send them to publishing channels",
    "current_problem": "The current page is split into four equal tall cards, making the workflow rigid, ugly, and hard to operate. The redesign should feel like a dense but calm production workbench."
  },
  "canvas": {
    "aspect_ratio": "16:10 desktop web app screenshot",
    "background": "light operational dashboard, #F4F6F8 with white panels",
    "framework_feel": "Ant Design compatible, compact controls, 8px radius, restrained teal accent"
  },
  "layout": {
    "left_sidebar": "fixed light sidebar with app brand, menu items, and service status, narrow but readable",
    "top_header": "project title, selected project metadata, health/status tag, primary project actions",
    "top_project_bar": "selected project dropdown, compact KPI chips for source videos, generated assets, running tasks, and latest output",
    "main_grid": "two-column workbench: left column is primary workflow, right column is result and publishing panel",
    "primary_workflow_left": [
      "large upload drop zone at the top with folder button and clear helper text",
      "generation configuration strip below: template select, source count chips, primary generate button",
      "source video table compactly listed below with selectable rows"
    ],
    "result_panel_right": [
      "latest output preview placeholder or video tile",
      "asset list with filters and actions preview/download/publish",
      "publish card pinned under latest asset, disabled empty state when no asset"
    ],
    "bottom_area": "recent pipeline runs table spanning full width, with status tags, progress text, and details action"
  },
  "style": {
    "visual_direction": "quiet utilitarian creative-ops console, not a marketing page",
    "typography": "system sans, compact headings, no huge hero type",
    "color_palette": {
      "surface": "#FFFFFF",
      "background": "#F4F6F8",
      "text": "#18202A",
      "muted": "#667085",
      "line": "#D9DEE7",
      "accent": "#0F766E",
      "accent_soft": "#E8F5F3",
      "warning": "#D97706",
      "success": "#16A34A"
    },
    "components": "Ant Design select, buttons, tags, table, upload dragger, empty states, drawer entry points",
    "density": "dashboard-dense but breathable, consistent 16px gaps, no nested decorative cards",
    "radius": "8px maximum for most UI"
  },
  "interaction_intent": {
    "primary_action": "Generate video should be visually obvious after upload",
    "secondary_actions": "Refresh status, preview latest video, publish latest video",
    "empty_states": "Clearly show no project, no videos, no assets, and no runs without looking broken",
    "mobile_behavior": "single-column stacking with upload, generate, results, publish, runs in that order"
  },
  "constraints": {
    "must_keep": [
      "Ant Design style controls",
      "light theme",
      "teal accent",
      "production dashboard feel",
      "workflow from upload to generate to preview to publish visible without hunting"
    ],
    "avoid": [
      "marketing hero layout",
      "decorative gradients or orbs",
      "purple-blue one-note palette",
      "huge equal-height cards",
      "overly dark cinema UI",
      "nested cards inside cards",
      "text overlap or tiny unreadable UI labels"
    ]
  }
}
