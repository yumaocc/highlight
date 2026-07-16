export type StatusType = 'default' | 'success' | 'warning' | 'error';

export type TaskStatus = {
  text: string;
  type: StatusType;
};

export type ProgressState = {
  percent: number;
  text: string;
};

export type Health = {
  ok: boolean;
  input_dir: string;
  output_dir: string;
  openai?: {
    api_key_configured?: boolean;
    text_model?: string;
  };
  gemini?: {
    api_key_configured?: boolean;
    model?: string;
  };
};

export type ModelUsageNode = {
  key: string;
  name: string;
  stage: string;
  provider: 'openai' | 'gemini' | 'dynamic';
  model_field: string;
  description: string;
};

export type ModelSettings = {
  openai: {
    api_key_configured: boolean;
    base_url: string;
    text_model: string;
    image_model: string;
    wire_api: 'responses' | 'chat_completions';
    transcribe_model: string;
  };
  gemini: {
    api_key_configured: boolean;
    base_url: string;
    model: string;
    tts_model: string;
    tts_voice: string;
    api_style: 'native' | 'openai';
  };
  transcribe_provider: 'gemini' | 'openai';
  usage_nodes: ModelUsageNode[];
};

export type ModelSettingsUpdate = {
  openai_api_key?: string;
  clear_openai_api_key?: boolean;
  openai_base_url: string;
  openai_text_model: string;
  openai_image_model: string;
  openai_wire_api: 'responses' | 'chat_completions';
  openai_transcribe_model: string;
  gemini_api_key?: string;
  clear_gemini_api_key?: boolean;
  gemini_base_url: string;
  gemini_model: string;
  gemini_tts_model: string;
  gemini_tts_voice: string;
  gemini_api_style: 'native' | 'openai';
  transcribe_provider: 'gemini' | 'openai';
};

export type Project = {
  id: number;
  name: string;
  description?: string;
  status: string;
  video_count?: number;
  asset_count?: number;
  created_at?: string;
  updated_at?: string;
};

export type Clip = {
  id: number;
  output_path?: string;
  start_seconds: number;
  end_seconds: number;
  reason?: string;
};

export type Video = {
  id: number;
  project_id?: number;
  name: string;
  path?: string;
  size_bytes?: number;
  duration?: number;
  width?: number;
  height?: number;
  fps?: number;
  codec?: string;
  clips?: Clip[];
};

export type GeneratedAsset = {
  id: number;
  project_id: number;
  source_video_id?: number;
  source_video_name?: string;
  clip_id?: number;
  pipeline_run_id?: number;
  pipeline_step_id?: number;
  type: 'highlight' | 'promo' | 'clip' | 'quality_cut' | string;
  title: string;
  description?: string;
  output_path: string;
  download_url: string;
  duration?: number;
  status: string;
  metadata?: any;
  created_at?: string;
};

export type PipelineTemplate = {
  key: string;
  name: string;
  description?: string;
  input_scope: 'single_video' | 'multi_video' | 'project' | string;
  output_cardinality: 'one' | 'many' | string;
  run_strategy?: 'per_source' | 'aggregate' | 'project_level' | string;
  steps: string[];
  params_schema?: Record<string, any>;
};

export type PipelineStep = {
  id: number;
  run_id: number;
  project_id: number;
  source_video_id?: number;
  step_key: string;
  name: string;
  order_index: number;
  status: string;
  progress: number;
  input?: any;
  output?: any;
  error?: string;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
};

export type PipelineRun = {
  id: number;
  project_id: number;
  source_video_id?: number;
  source_video_name?: string;
  source_count?: number;
  sources?: Array<{ source_video_id: number; source_video_name?: string; order_index: number; role?: string }>;
  template_key: string;
  status: string;
  current_step?: string;
  progress: number;
  params?: any;
  prompt_snapshot?: any;
  result?: any;
  error?: string;
  steps?: PipelineStep[];
  created_at?: string;
  updated_at?: string;
  started_at?: string;
  finished_at?: string;
};

export type PipelineArtifact = {
  id: number;
  project_id: number;
  source_video_id?: number;
  pipeline_run_id: number;
  pipeline_step_id?: number;
  type: string;
  title?: string;
  path?: string;
  content?: any;
  metadata?: any;
  is_final?: boolean;
  created_at?: string;
};

export type PipelineRunCreatePayload = {
  template_key: string;
  source_video_ids: number[];
  params?: Record<string, any>;
  prompt_config_ids?: number[];
};

export type ResourceImportTask = {
  id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | string;
  progress: number;
  message: string;
  project_id: number;
  project_name?: string;
  baidu_url: string;
  extract_code?: string;
  drama_name?: string;
  episode_limit: number;
  pipeline_template_key: string;
  downloaded: Array<{
    name: string;
    remote_path: string;
    local_path: string;
    size_bytes: number;
    episode_number?: number;
  }>;
  selected: Array<{
    name: string;
    remote_path: string;
    size?: number;
    episode_number?: number;
  }>;
  scan?: { indexed: number; failed: string[] } | null;
  video_ids: number[];
  pipeline_runs: PipelineRun[];
  error?: string;
  logs: Array<{ time: string; level: string; message: string }>;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
};

export type ResourceImportCreatePayload = {
  project_id: number;
  baidu_url: string;
  extract_code?: string;
  drama_name?: string;
  episode_limit?: number;
  recursive?: boolean;
  max_depth?: number;
  pipeline_template_key?: string;
  enqueue_pipeline?: boolean;
};

export type QingqueResourceMatch = {
  drama_name: string;
  baidu_url: string;
  extract_code: string;
  raw_link_text: string;
  sheet_id: string;
  sheet_name: string;
  row: number;
  score: number;
  match_type: string;
};

export type AutoPublishItem = {
  name: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | string;
  progress: number;
  message: string;
  error?: string;
  project_id?: number;
  remote_dir?: string;
  resource?: QingqueResourceMatch;
  downloaded?: any[];
  video_ids?: number[];
  pipeline_run_ids?: number[];
  asset_paths?: string[];
  publish_task?: any;
  existing_record?: AutoPublishRecord;
  timings?: Record<string, { label: string; seconds: number; display: string; finished_at?: string }>;
  duration_seconds?: number;
  duration_display?: string;
};

export type AutoPublishTask = {
  id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | string;
  progress: number;
  message: string;
  total: number;
  completed: number;
  items: AutoPublishItem[];
  logs: Array<{ time: string; message: string }>;
  created_at?: string;
  started_at?: string;
  finished_at?: string;
};

export type AutoPublishRecord = {
  id: number;
  drama_name: string;
  normalized_name: string;
  status: string;
  project_id?: number;
  auto_task_id: string;
  publish_task_id: string;
  message: string;
  metadata?: any;
  created_at: string;
  updated_at: string;
};

export type AutoPublishCreatePayload = {
  drama_names: string[];
  episode_limit?: number;
  pipeline_template_key?: string;
  publish_enabled?: boolean;
  publish_base_url?: string;
  platform?: string;
  account_ids?: string[];
  topics?: string[];
  is_original?: boolean;
  schedule_at?: string;
  kuaishou_enable_promotion_task?: boolean;
  skip_existing?: boolean;
  max_concurrency?: number;
};

export type ContentPromotionResult = {
  title: string;
  content: string;
  topics: string[];
  strategy: string;
  image_prompt: string;
  image_path: string;
  image_url: string;
  image_result?: any;
};

export type ContentPromotionGeneratePayload = {
  description: string;
  audience?: string;
  tone?: string;
  platform?: string;
};

export type TraceMessage = {
  role: 'system' | 'model' | 'result';
  title: string;
  body: string;
  meta?: string;
  percent?: number;
};

export type Trace =
  | { kind: 'empty'; data: null }
  | { kind: 'messages'; data: TraceMessage[] }
  | { kind: 'highlights'; data: any[] }
  | { kind: 'promo'; data: any };

export type StreamEvent =
  | (TraceMessage & { type: 'message' })
  | { type: 'trace'; trace: Trace }
  | { type: 'done'; result: any; percent?: number }
  | { type: 'error'; message: string };

export type StreamHandlers<T = any> = {
  onMessage?: (message: TraceMessage) => void;
  onTrace?: (trace: Trace) => void;
  onProgress?: (percent: number, text: string) => void;
  onDone?: (result: T) => void;
};
