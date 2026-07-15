import { ClearOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons';
import { Button, Card, Progress, Space, Statistic, Typography } from 'antd';
import type { ProgressState, TaskStatus } from '@/types/dashboard';
import { formatElapsed } from '@/utils/format';

const { Text } = Typography;

type TaskProgressCardProps = {
  busy: boolean;
  elapsed: number;
  progress: ProgressState;
  status: TaskStatus;
  onAbort: () => void;
  onRefresh: () => void;
  onReset: () => void;
  onClearTrace: () => void;
};

export function TaskProgressCard({ busy, elapsed, progress, status, onAbort, onRefresh, onReset, onClearTrace }: TaskProgressCardProps) {
  return (
    <Card title="任务进度" extra={<Statistic value={formatElapsed(elapsed)} valueStyle={{ fontSize: 14 }} />}>
      <Space wrap className="debug-actions">
        <Button danger icon={<StopOutlined />} onClick={onAbort}>
          停止当前请求
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          刷新列表
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onReset}>
          重置进度
        </Button>
        <Button icon={<ClearOutlined />} onClick={onClearTrace}>
          清空模型日志
        </Button>
      </Space>
      <Progress percent={progress.percent} status={status.type === 'error' ? 'exception' : busy ? 'active' : 'normal'} />
      <Text type="secondary">{progress.text}</Text>
    </Card>
  );
}
