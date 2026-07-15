import { Button, Card, Empty, List, Popconfirm, Space, Tag, Typography, message } from 'antd';
import { DeleteOutlined, LoginOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { getHealth } from '@/services/api';
import {
  deletePublishAccount,
  fallbackAccounts,
  getPublishAccounts,
  type PublishAccount,
} from '@/services/publish';
import type { Health } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Paragraph, Text } = Typography;

export default function AccountsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [accounts, setAccounts] = useState<PublishAccount[]>(fallbackAccounts);
  const [serviceReady, setServiceReady] = useState(false);
  const [deletingId, setDeletingId] = useState<string | number | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
    loadAccounts();
  }, []);

  async function loadAccounts() {
    try {
      const data = await getPublishAccounts();
      setAccounts(data);
      setServiceReady(true);
    } catch (error) {
      setAccounts(fallbackAccounts);
      setServiceReady(false);
    }
  }

  function openLoginPage(account?: PublishAccount) {
    const params = new URLSearchParams();
    params.set('platform', account?.platform || 'douyin');
    if (account?.name) params.set('accountName', account.name);
    const loginUrl = `/accounts/login?${params.toString()}`;
    const loginWindow = window.open(loginUrl, '_blank');
    if (loginWindow) {
      loginWindow.focus();
      return;
    }
    window.location.href = loginUrl;
  }

  async function removeAccount(account: PublishAccount) {
    setDeletingId(account.id);
    try {
      await deletePublishAccount(account);
      setAccounts((items) => items.filter((item) => item.id !== account.id));
      message.success('账号已删除');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <WorkspaceLayout
      health={health}
      title="平台账号"
      subtitle="管理各平台账号、登录状态和默认发布配置。"
      actions={
        <Space>
          <Tag color={serviceReady ? 'success' : 'warning'}>{serviceReady ? '发布服务已连接' : '等待 publish-service'}</Tag>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openLoginPage()}>
            添加登录
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadAccounts}>
            刷新
          </Button>
        </Space>
      }
    >
      <Card>
        <List
          dataSource={accounts}
          locale={{ emptyText: <Empty description="暂无账号数据" /> }}
          renderItem={(account) => (
            <List.Item
              actions={[
                <Button key="login" icon={<LoginOutlined />} disabled={!serviceReady} onClick={() => openLoginPage(account)}>
                  重新登录
                </Button>,
                <Popconfirm
                  key="delete"
                  title="删除账号？"
                  description={`会删除 ${account.platform} / ${account.name} 的登录态 Cookie。`}
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => removeAccount(account)}
                  disabled={!serviceReady}
                >
                  <Button danger icon={<DeleteOutlined />} disabled={!serviceReady} loading={deletingId === account.id}>
                    删除
                  </Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Text strong>{account.name}</Text>
                    <Tag>{account.platform}</Tag>
                    <Tag color={account.status === '可用' || account.status === 'valid' ? 'success' : 'warning'}>{account.status}</Tag>
                  </Space>
                }
                description={
                  <Paragraph className="compact-paragraph">
                    {account.remark || 'publish-service 接入后，这里会显示登录态、cookie 过期时间和账号备注。'}
                  </Paragraph>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </WorkspaceLayout>
  );
}
