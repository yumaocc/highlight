import { DownloadOutlined } from '@ant-design/icons';
import { Button, Card, Empty, List } from 'antd';
import type { Clip } from '@/types/dashboard';

export function ClipListCard({ clips }: { clips: Clip[] }) {
  return (
    <Card title="高光视频">
      <ClipList clips={clips} />
    </Card>
  );
}

function ClipList({ clips }: { clips: Clip[] }) {
  if (!clips.length) return <Empty description="暂无片段" />;
  return (
    <List
      dataSource={clips}
      renderItem={(clip) => (
        <List.Item
          actions={[
            <Button key="download" type="link" href={`/api/clips/${clip.id}/download`} icon={<DownloadOutlined />}>
              下载
            </Button>,
          ]}
        >
          <List.Item.Meta title={`${Number(clip.start_seconds).toFixed(2)}s - ${Number(clip.end_seconds).toFixed(2)}s`} description={clip.reason || '手动导出'} />
        </List.Item>
      )}
    />
  );
}
