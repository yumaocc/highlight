import { requestJson } from './api';

export type PublishPlatform = {
  key: string;
  name: string;
  supportsVideo: boolean;
  supportsImageText: boolean;
  supportsSchedule: boolean;
};

export type PublishAccount = {
  id: string | number;
  name: string;
  platform: string;
  status: string;
  remark?: string;
  filePath?: string;
};

export type PublishTask = {
  id: string;
  title: string;
  platform: string;
  accountNames: string[];
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled';
  message?: string;
  createdAt: string;
};

export type CreatePublishTaskPayload = {
  platform: string;
  accountIds: Array<string | number>;
  filePaths: string[];
  title: string;
  description?: string;
  topics: string[];
  isOriginal: boolean;
  scheduleAt?: string;
  kuaishouEnablePromotionTask?: boolean;
  kuaishouPromotionTaskTitle?: string;
};

export async function getPublishPlatforms() {
  return requestJson<PublishPlatform[]>('/publish-api/platforms').catch(() => fallbackPlatforms);
}

export async function getPublishAccounts() {
  return requestJson<PublishAccount[]>('/publish-api/accounts');
}

export async function deletePublishAccount(account: Pick<PublishAccount, 'platform' | 'name'>) {
  const params = new URLSearchParams({ accountName: account.name });
  return requestJson<{ deleted: boolean }>(`/publish-api/accounts/${account.platform}?${params.toString()}`, {
    method: 'DELETE',
  });
}

export async function getPublishTasks() {
  return requestJson<PublishTask[]>('/publish-api/tasks').catch(() => []);
}

export async function createPublishTask(payload: CreatePublishTaskPayload) {
  return requestJson<PublishTask>('/publish-api/publish/video', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export type CreateNotePublishTaskPayload = {
  platform: string;
  accountIds: Array<string | number>;
  imagePaths: string[];
  title: string;
  content: string;
  topics: string[];
  scheduleAt?: string;
};

export async function createNotePublishTask(payload: CreateNotePublishTaskPayload) {
  return requestJson<PublishTask>('/publish-api/publish/note', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export type AccountLoginEvent =
  | { type: 'qrcode'; imageUrl: string }
  | { type: 'success'; message: string; raw?: any }
  | { type: 'error'; message: string; raw?: any }
  | { type: 'status'; message: string; raw?: any };

export type AccountLoginPayload = {
  platform: string;
  accountName: string;
};

export function startAccountLogin(
  payload: AccountLoginPayload,
  onEvent: (event: AccountLoginEvent) => void,
) {
  const params = new URLSearchParams({ accountName: payload.accountName });
  const controller = new AbortController();
  let closed = false;

  const emit = (event: AccountLoginEvent) => {
    if (!closed) onEvent(event);
  };

  (async () => {
    try {
      emit({ type: 'status', message: '前端已发起登录请求，正在连接 publish-service...' });
      const response = await fetch(`/publish-api/accounts/${payload.platform}/login?${params.toString()}`, {
        headers: { Accept: 'text/event-stream' },
        signal: controller.signal,
      });
      emit({ type: 'status', message: `publish-service 已响应：HTTP ${response.status}` });

      if (!response.ok) {
        emit({ type: 'error', message: await readLoginError(response) });
        return;
      }

      if (!response.body) {
        emit({ type: 'error', message: '登录连接没有返回可读取的输出流' });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() || '';
        for (const part of parts) {
          const parsed = parseLoginSseBlock(part);
          if (parsed) emit(parsed);
          if (!parsed && part.trim()) emit({ type: 'status', message: part.trim() });
        }
      }

      buffer += decoder.decode();
      const parsed = parseLoginSseBlock(buffer);
      if (parsed) emit(parsed);
      if (!parsed && buffer.trim()) emit({ type: 'status', message: buffer.trim() });
    } catch (error) {
      if (!controller.signal.aborted) {
        emit({ type: 'error', message: error instanceof Error ? error.message : '登录连接已断开' });
      }
    }
  })();

  return () => {
    closed = true;
    controller.abort();
  };
}

function parseLoginSseBlock(block: string): AccountLoginEvent | null {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.replace(/^data:\s?/, ''))
    .join('\n')
    .trim();
  return data ? parseLoginEvent(data) : null;
}

async function readLoginError(response: Response) {
  const text = await response.text();
  try {
    const data = JSON.parse(text);
    return data.detail || data.message || text || `登录请求失败：${response.status}`;
  } catch {
    return text || `登录请求失败：${response.status}`;
  }
}

function parseLoginEvent(data: string): AccountLoginEvent {
  try {
    const parsed = JSON.parse(data);
    if (parsed.type === 'qrcode') return { type: 'qrcode', imageUrl: parsed.imageUrl };
    if (parsed.type === 'success') return { type: 'success', message: parsed.message || '登录成功', raw: parsed };
    if (parsed.type === 'error') return { type: 'error', message: parsed.message || '登录失败', raw: parsed };
    return { type: 'status', message: parsed.message || data || '等待扫码', raw: parsed };
  } catch {
    return { type: 'status', message: data || '等待扫码' };
  }
}

export const fallbackPlatforms: PublishPlatform[] = [
  { key: 'douyin', name: '抖音', supportsVideo: true, supportsImageText: true, supportsSchedule: true },
  { key: 'xiaohongshu', name: '小红书', supportsVideo: true, supportsImageText: true, supportsSchedule: true },
  { key: 'kuaishou', name: '快手', supportsVideo: true, supportsImageText: true, supportsSchedule: true },
  { key: 'wechat_channels', name: '视频号', supportsVideo: true, supportsImageText: false, supportsSchedule: true },
  { key: 'bilibili', name: 'Bilibili', supportsVideo: true, supportsImageText: false, supportsSchedule: true },
  { key: 'youtube', name: 'YouTube', supportsVideo: true, supportsImageText: false, supportsSchedule: false },
];

export const fallbackAccounts: PublishAccount[] = [
  { id: 'douyin-default', name: '抖音账号', platform: 'douyin', status: '待接入' },
  { id: 'xhs-default', name: '小红书账号', platform: 'xiaohongshu', status: '待接入' },
];
