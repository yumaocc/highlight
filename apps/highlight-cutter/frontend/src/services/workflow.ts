import { requestJson } from './api';
import type { GeneratedAsset } from '@/types/dashboard';

export type IntroTemplate = {
  id: number;
  name: string;
  drama_name: string;
  style: string;
  summary: string;
  duration: number;
  asset_path: string;
  image_path: string;
  image_url: string;
  intro_image_path: string;
  intro_image_url: string;
  outro_image_path: string;
  outro_image_url: string;
  prompt: string;
  source: 'manual' | 'ai';
  status: 'ready' | 'draft';
  created_at: string;
  updated_at: string;
};

export type IntroTemplatePayload = {
  name: string;
  drama_name?: string;
  style?: string;
  summary?: string;
  duration?: number;
  asset_path?: string;
  image_path?: string;
  image_url?: string;
  intro_image_path?: string;
  intro_image_url?: string;
  outro_image_path?: string;
  outro_image_url?: string;
  prompt?: string;
  source?: 'manual' | 'ai';
  status?: 'ready' | 'draft';
};

export type IntroTemplateAsset = {
  filename: string;
  path: string;
  url: string;
};

export type IntroTemplateVisualPayload = {
  kind: 'intro' | 'outro';
  drama_name: string;
  style?: string;
  brief?: string;
  duration?: number;
  reference_image_path?: string;
  template_id?: number;
};

export type IntroTemplateVisualResult = {
  ok: boolean;
  kind: 'intro' | 'outro';
  mode: 'generation' | 'edit';
  model: string;
  prompt: string;
  output_path: string;
  path: string;
  url: string;
  video_path?: string;
  video_url?: string;
  orchestration?: {
    gemini?: any;
    gpt?: any;
    video?: any;
  };
  template?: IntroTemplate;
};

export type IntroWorkflowRunPayload = {
  template_id: number;
  source_video_ids: number[];
};

export type IntroWorkflowRunResult = {
  id?: string;
  status?: IntroWorkflowTaskStatus;
  progress?: number;
  message?: string;
  logs?: IntroWorkflowTaskLog[];
  generated: GeneratedAsset[];
  failed: Array<{ video_id: number; error: string }>;
};

export type IntroWorkflowTaskStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'partial';

export type IntroWorkflowTaskLog = {
  time: string;
  level: 'info' | 'error' | string;
  message: string;
};

export type IntroWorkflowTask = {
  id: string;
  status: IntroWorkflowTaskStatus;
  progress: number;
  message: string;
  template_id: number;
  template_name: string;
  source_video_ids: number[];
  generated: GeneratedAsset[];
  failed: Array<{ video_id: number; error: string }>;
  logs: IntroWorkflowTaskLog[];
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export function getIntroTemplates() {
  return requestJson<IntroTemplate[]>('/api/intro-templates');
}

export function createIntroTemplate(payload: IntroTemplatePayload) {
  return requestJson<IntroTemplate>('/api/intro-templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function updateIntroTemplate(templateId: number, payload: Partial<IntroTemplatePayload>) {
  return requestJson<IntroTemplate>(`/api/intro-templates/${templateId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function deleteIntroTemplate(templateId: number) {
  return requestJson<{ deleted: boolean; id: number }>(`/api/intro-templates/${templateId}`, {
    method: 'DELETE',
  });
}

export function uploadIntroTemplateAsset(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return requestJson<IntroTemplateAsset>('/api/intro-template-assets', {
    method: 'POST',
    body: formData,
  });
}

export function generateIntroTemplateVisual(payload: IntroTemplateVisualPayload) {
  return requestJson<IntroTemplateVisualResult>('/api/intro-templates/visuals/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function runIntroWorkflow(payload: IntroWorkflowRunPayload) {
  return requestJson<IntroWorkflowTask>('/api/intro-workflow/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getIntroWorkflowTask(taskId: string) {
  return requestJson<IntroWorkflowTask>(`/api/intro-workflow/tasks/${taskId}`);
}
