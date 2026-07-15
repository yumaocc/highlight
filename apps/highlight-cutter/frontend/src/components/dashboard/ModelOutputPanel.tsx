import { ClearOutlined } from '@ant-design/icons';
import { Button, Collapse, Empty, Space, Typography } from 'antd';
import { TraceChat } from '@/components/trace/TraceChat';
import type { Trace, TraceMessage } from '@/types/dashboard';

const { Text } = Typography;

type ModelOutputPanelProps = {
  trace: Trace;
  messages?: TraceMessage[];
  onClearTrace: () => void;
};

export function ModelOutputPanel({ trace, messages = [], onClearTrace }: ModelOutputPanelProps) {
  const displayTrace: Trace = messages.length ? { kind: 'messages', data: messages } : trace;
  const content =
    displayTrace.kind === 'empty' ? (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Space direction="vertical" size={2}>
            <Text>生成后显示模型判断</Text>
            <Text type="secondary">本地峰值、台词分析、画面复评和复核结果会集中在这里。</Text>
          </Space>
        }
      />
    ) : (
      <TraceChat trace={displayTrace} />
    );

  return (
    <Collapse
      className="focus-collapse"
      defaultActiveKey={['model-output']}
      items={[
        {
          key: 'model-output',
          label: '模型输出',
          extra: (
            <Button
              size="small"
              icon={<ClearOutlined />}
              onClick={(event) => {
                event.stopPropagation();
                onClearTrace();
              }}
            >
              清空
            </Button>
          ),
          children: content,
        },
      ]}
    />
  );
}
