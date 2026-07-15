import { formatSize } from '@/utils/format';

type UploadProgressHandlers = {
  onUnknownProgress: () => void;
  onProgress: (percent: number, weightedPercent: number, hint: string) => void;
  onFinished?: (xhr: XMLHttpRequest) => void;
};

export function uploadVideosWithProgress(
  files: File[],
  xhrRef: { current: XMLHttpRequest | null },
  handlers: UploadProgressHandlers,
  projectId?: number | null,
) {
  return new Promise<{ saved: string[] }>((resolve, reject) => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));

    const xhr = new XMLHttpRequest();
    xhrRef.current = xhr;
    const params = new URLSearchParams();
    if (projectId) params.set('project_id', String(projectId));
    xhr.open('POST', `/api/upload${params.toString() ? `?${params.toString()}` : ''}`);
    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable) {
        handlers.onUnknownProgress();
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      const weighted = Math.min(70, Math.max(10, Math.round(percent * 0.7)));
      handlers.onProgress(percent, weighted, `已上传 ${formatSize(event.loaded)} / ${formatSize(event.total)}`);
    });
    xhr.addEventListener('load', () => {
      let payload = {};
      try {
        payload = JSON.parse(xhr.responseText || '{}');
      } catch {
        reject(new Error('上传响应解析失败'));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload as { saved: string[] });
      else reject(new Error((payload as any).detail || xhr.statusText || '上传失败'));
    });
    xhr.addEventListener('error', () => reject(new Error('上传请求失败')));
    xhr.addEventListener('abort', () => reject(new Error('上传已取消')));
    xhr.addEventListener('loadend', () => {
      if (xhrRef.current === xhr) xhrRef.current = null;
      handlers.onFinished?.(xhr);
    });
    xhr.send(formData);
  });
}
