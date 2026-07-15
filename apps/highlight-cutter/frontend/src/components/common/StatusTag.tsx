import { Tag } from 'antd';
import type { TaskStatus } from '@/types/dashboard';

export function StatusTag({ status }: { status: TaskStatus }) {
  const color = status.type === 'error' ? 'red' : status.type === 'success' ? 'green' : status.type === 'warning' ? 'gold' : 'default';
  return <Tag color={color}>{status.text}</Tag>;
}
