import type {
  GeneratedAsset,
  Health,
  AutoPublishCreatePayload,
  AutoPublishRecord,
  AutoPublishTask,
  PipelineArtifact,
  PipelineRun,
  PipelineRunCreatePayload,
  PipelineTemplate,
  Project,
  QingqueResourceMatch,
  ResourceImportCreatePayload,
  ResourceImportTask,
  StreamEvent,
  StreamHandlers,
  Video,
} from '@/types/dashboard';

export async function requestJson<T = any>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    if (typeof detail === 'string') throw new Error(detail);
    if (detail?.error) throw new Error(detail.error);
    throw new Error(response.statusText);
  }
  return payload;
}

export function getHealth() {
  return requestJson<Health>('/api/health');
}

export function getProjects() {
  return requestJson<Project[]>('/api/projects');
}

export function createProject(payload: { name: string; description?: string; status?: string }) {
  return requestJson<Project>('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function deleteProject(projectId: number) {
  return requestJson<{
    deleted: boolean;
    id: number;
    removed_videos: number;
    removed_assets: number;
    removed_runs: number;
    removed_input_files: number;
    removed_work_dirs: number;
    outputs_preserved: string;
    failed: string[];
  }>(`/api/projects/${projectId}`, { method: 'DELETE' });
}

export function getProjectAssets(projectId: number) {
  return requestJson<GeneratedAsset[]>(`/api/projects/${projectId}/assets`);
}

export function getPipelineTemplates() {
  return requestJson<PipelineTemplate[]>('/api/pipeline-templates');
}

export function getPipelineTemplate(templateKey: string) {
  return requestJson<PipelineTemplate>(`/api/pipeline-templates/${templateKey}`);
}

export function createPipelineRuns(projectId: number, payload: PipelineRunCreatePayload, enqueue = false) {
  const params = new URLSearchParams();
  if (enqueue) params.set('enqueue', 'true');
  const query = params.toString();
  return requestJson<{ runs: PipelineRun[] }>(`/api/projects/${projectId}/pipeline-runs${query ? `?${query}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getProjectPipelineRuns(projectId: number) {
  return requestJson<PipelineRun[]>(`/api/projects/${projectId}/pipeline-runs`);
}

function projectQuery(projectId?: number | null) {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', String(projectId));
  const query = params.toString();
  return query ? `?${query}` : '';
}

export function getPipelineRun(runId: number, projectId?: number | null) {
  return requestJson<PipelineRun>(`/api/pipeline-runs/${runId}${projectQuery(projectId)}`);
}

export function getPipelineRunSteps(runId: number, projectId?: number | null) {
  return requestJson<PipelineRun['steps']>(`/api/pipeline-runs/${runId}/steps${projectQuery(projectId)}`);
}

export function getPipelineRunArtifacts(runId: number, projectId?: number | null) {
  return requestJson<PipelineArtifact[]>(`/api/pipeline-runs/${runId}/artifacts${projectQuery(projectId)}`);
}

export function getPipelineRunGeneratedAssets(runId: number, projectId?: number | null) {
  return requestJson<GeneratedAsset[]>(`/api/pipeline-runs/${runId}/generated-assets${projectQuery(projectId)}`);
}

export function cancelPipelineRun(runId: number, projectId?: number | null) {
  return requestJson<PipelineRun>(`/api/pipeline-runs/${runId}/cancel${projectQuery(projectId)}`, { method: 'POST' });
}

export function getVideos(projectId?: number | null) {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', String(projectId));
  const query = params.toString();
  return requestJson<Video[]>(`/api/videos${query ? `?${query}` : ''}`);
}

export function getVideo(videoId: number, projectId?: number | null) {
  return requestJson<Video>(`/api/videos/${videoId}${projectQuery(projectId)}`);
}

export function scanVideos(projectId?: number | null) {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', String(projectId));
  const query = params.toString();
  return requestJson<{ indexed: number; failed: string[] }>(`/api/scan${query ? `?${query}` : ''}`, { method: 'POST' });
}

export function clearUploadedVideos(projectId?: number | null) {
  const params = new URLSearchParams();
  if (projectId) params.set('project_id', String(projectId));
  const query = params.toString();
  return requestJson<{
    removed_files: number;
    removed_work_files: number;
    failed: string[];
    outputs_preserved: string;
  }>(`/api/videos${query ? `?${query}` : ''}`, { method: 'DELETE' });
}

export function createResourceImport(payload: ResourceImportCreatePayload) {
  return requestJson<ResourceImportTask>('/api/resource-imports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getResourceImport(taskId: string) {
  return requestJson<ResourceImportTask>(`/api/resource-imports/${taskId}`);
}

export function searchQingqueResources(name: string, limit = 10, refresh = false) {
  const params = new URLSearchParams({ name, limit: String(limit) });
  if (refresh) params.set('refresh', 'true');
  return requestJson<QingqueResourceMatch[]>(`/api/qingque/resources/search?${params.toString()}`);
}

export function createAutoPublishTask(payload: AutoPublishCreatePayload) {
  return requestJson<AutoPublishTask>('/api/auto-publish/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getAutoPublishTask(taskId: string) {
  return requestJson<AutoPublishTask>(`/api/auto-publish/tasks/${taskId}`);
}

export function retryAutoPublishItem(taskId: string, itemIndex: number) {
  return requestJson<AutoPublishTask>(`/api/auto-publish/tasks/${taskId}/items/${itemIndex}/retry`, {
    method: 'POST',
  });
}

export function getAutoPublishRecords() {
  return requestJson<AutoPublishRecord[]>('/api/auto-publish/records');
}

export function checkAutoPublishRecord(name: string) {
  const params = new URLSearchParams({ name });
  return requestJson<{ exists: boolean; record?: AutoPublishRecord | null }>(`/api/auto-publish/records/check?${params.toString()}`);
}

export function generateHighlights(engine: string, limit: number, projectId?: number | null, signal?: AbortSignal) {
  const params = new URLSearchParams({ engine });
  if (limit > 0) params.set('limit', String(limit));
  if (projectId) params.set('project_id', String(projectId));
  return requestJson<{ generated: any[] }>(`/api/highlights/auto?${params.toString()}`, {
    method: 'POST',
    signal,
  });
}

export function generateHighlightsStream(
  engine: string,
  limit: number,
  projectId: number | null,
  handlers: StreamHandlers<{ generated: any[] }>,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ engine });
  if (limit > 0) params.set('limit', String(limit));
  if (projectId) params.set('project_id', String(projectId));
  return requestNdjsonStream<{ generated: any[] }>(`/api/highlights/auto/stream?${params.toString()}`, handlers, signal);
}

export function generatePromo(limit: number, windowsPerVideo: number, projectId?: number | null, signal?: AbortSignal) {
  const params = new URLSearchParams({ limit: String(limit), windows_per_video: String(windowsPerVideo) });
  if (projectId) params.set('project_id', String(projectId));
  return requestJson<any>(`/api/promos/generate?${params.toString()}`, {
    method: 'POST',
    signal,
  });
}

export function generatePromoStream(
  limit: number,
  windowsPerVideo: number,
  projectId: number | null,
  handlers: StreamHandlers<any>,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ limit: String(limit), windows_per_video: String(windowsPerVideo) });
  if (projectId) params.set('project_id', String(projectId));
  return requestNdjsonStream<any>(`/api/promos/generate/stream?${params.toString()}`, handlers, signal);
}

async function requestNdjsonStream<T>(
  url: string,
  handlers: StreamHandlers<T>,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, { method: 'POST', signal });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || response.statusText);
  }
  if (!response.body) throw new Error('stream response body is empty');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: T | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const parsed = JSON.parse(line) as StreamEvent;
        if (parsed.type === 'message') {
          const { role, title, body, meta, percent } = parsed;
          handlers.onMessage?.({ role, title, body, meta, percent });
          if (typeof percent === 'number') handlers.onProgress?.(percent, title);
        } else if (parsed.type === 'trace') {
          handlers.onTrace?.(parsed.trace);
        } else if (parsed.type === 'done') {
          result = parsed.result as T;
          handlers.onDone?.(result);
          if (typeof parsed.percent === 'number') handlers.onProgress?.(parsed.percent, '任务完成');
        } else if (parsed.type === 'error') {
          throw new Error(parsed.message);
        }
      }
    }
    if (done) break;
  }

  if (buffer.trim()) {
    const parsed = JSON.parse(buffer) as StreamEvent;
    if (parsed.type === 'done') result = parsed.result as T;
    if (parsed.type === 'error') throw new Error(parsed.message);
  }
  if (result === null) throw new Error('stream ended without result');
  return result;
}
