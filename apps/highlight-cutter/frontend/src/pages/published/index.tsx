import { App, Button, Card, List, Space, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { getAutoPublishRecords, getHealth } from '@/services/api';
import type { AutoPublishRecord, Health } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Text } = Typography;

export default function PublishedPage() {
  const { message } = App.useApp();
  const [health, setHealth] = useState<Health | null>(null);
  const [records, setRecords] = useState<AutoPublishRecord[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadHealth();
    loadRecords();
  }, []);

  async function loadHealth() {
    setHealth(await getHealth().catch(() => null));
  }

  async function loadRecords() {
    setLoading(true);
    try {
      setRecords(await getAutoPublishRecords());
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <WorkspaceLayout
      health={health}
      title="已发布短剧"
      subtitle={<Text type="secondary">发布完成后会记录短剧名称，用于下次发布前去重提醒。</Text>}
      actions={<Button icon={<ReloadOutlined />} onClick={loadRecords} loading={loading}>刷新</Button>}
    >
      <Card>
        <List
          className="published-drama-list"
          loading={loading}
          dataSource={records}
          locale={{ emptyText: '暂无已发布短剧' }}
          renderItem={(record) => (
            <List.Item>
              <div className="published-drama-item">
                <div className="published-drama-main">
                  <Text strong>{record.drama_name}</Text>
                  <Space size={6} wrap>
                    <Tag color="green">已发布</Tag>
                    {record.project_id && <Tag>项目 {record.project_id}</Tag>}
                    {record.publish_task_id && <Tag>发布任务 {record.publish_task_id.slice(0, 8)}</Tag>}
                  </Space>
                </div>
                <div className="published-drama-meta">
                  <Text type="secondary">{record.message || '已记录'}</Text>
                  <Text type="secondary">{record.updated_at || record.created_at}</Text>
                </div>
              </div>
            </List.Item>
          )}
        />
      </Card>
    </WorkspaceLayout>
  );
}
