import { DeleteOutlined } from '@ant-design/icons';
import { Button, Collapse, Empty, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import type { Video } from '@/types/dashboard';
import { formatDuration, formatSize } from '@/utils/format';

type VideoTableCardProps = {
  busy: boolean;
  videos: Video[];
  selectedVideoId: number | null;
  onSelectVideo: (videoId: number) => void;
  onClearVideos: () => void;
};

export function VideoTableCard({ busy, videos, selectedVideoId, onSelectVideo, onClearVideos }: VideoTableCardProps) {
  const [activeKeys, setActiveKeys] = useState<string[]>(videos.length ? ['source-list'] : []);

  useEffect(() => {
    setActiveKeys(videos.length ? ['source-list'] : []);
  }, [videos.length]);

  const columns: ColumnsType<Video> = [
    {
      title: '文件名',
      dataIndex: 'name',
      ellipsis: true,
      render: (value: string, record) => (
        <Button type="link" className="row-link" onClick={() => onSelectVideo(record.id)}>
          {value}
        </Button>
      ),
    },
    { title: '时长', dataIndex: 'duration', width: 96, render: formatDuration },
    { title: '大小', dataIndex: 'size_bytes', width: 110, render: formatSize },
    { title: '分辨率', width: 112, render: (_, record) => `${record.width || 0}x${record.height || 0}` },
  ];

  return (
    <Collapse
      className="source-list-collapse"
      activeKey={activeKeys}
      onChange={(keys) => setActiveKeys(Array.isArray(keys) ? keys : [keys])}
      items={[
        {
          key: 'source-list',
          label: '素材列表',
          extra: (
            <Space onClick={(event) => event.stopPropagation()}>
              <Tag>{videos.length} 个视频</Tag>
              <Button danger size="small" icon={<DeleteOutlined />} onClick={onClearVideos} disabled={busy}>
                清空已上传
              </Button>
            </Space>
          ),
          children: (
            <Table
              size="small"
              rowKey="id"
              columns={columns}
              dataSource={videos}
              pagination={videos.length > 5 ? { pageSize: 5, showSizeChanger: false } : false}
              rowClassName={(record) => (record.id === selectedVideoId ? 'selected-row' : '')}
              locale={{ emptyText: <Empty description="还没有视频" /> }}
            />
          ),
        },
      ]}
    />
  );
}
