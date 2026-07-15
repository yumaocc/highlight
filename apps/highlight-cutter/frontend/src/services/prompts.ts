import { requestJson } from './api';

export type PromptConfig = {
  id: number;
  key: string;
  name: string;
  category: string;
  description: string;
  content: string;
  enabled: boolean;
  is_system: boolean;
  created_at: string;
  updated_at: string;
};

export type PromptConfigPayload = {
  key: string;
  name: string;
  category: string;
  description?: string;
  content: string;
  enabled: boolean;
};

export type PromptConfigUpdate = Partial<Omit<PromptConfigPayload, 'key'>>;

export function getPromptConfigs(category = 'video_generation') {
  const params = new URLSearchParams({ category });
  return requestJson<PromptConfig[]>(`/api/prompts?${params.toString()}`);
}

export function createPromptConfig(payload: PromptConfigPayload) {
  return requestJson<PromptConfig>('/api/prompts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function updatePromptConfig(promptId: number, payload: PromptConfigUpdate) {
  return requestJson<PromptConfig>(`/api/prompts/${promptId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function deletePromptConfig(promptId: number) {
  return requestJson<{ deleted: boolean; id: number }>(`/api/prompts/${promptId}`, {
    method: 'DELETE',
  });
}
