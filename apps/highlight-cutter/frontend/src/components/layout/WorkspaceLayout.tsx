import { AppstoreOutlined, CheckCircleOutlined, CloudUploadOutlined, NotificationOutlined, RobotOutlined, ScissorOutlined, UserSwitchOutlined } from '@ant-design/icons';
import { Layout, Menu, Typography } from 'antd';
import type { ReactNode } from 'react';
import { history, useLocation } from '@umijs/max';
import type { Health } from '@/types/dashboard';
import { AppSidebar } from './AppSidebar';

const { Header, Sider, Content } = Layout;
const { Text, Title } = Typography;

type WorkspaceLayoutProps = {
  health?: Health | null;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
};

const menuItems = [
  { key: '/', icon: <ScissorOutlined />, label: '自动发布' },
  { key: '/published', icon: <CheckCircleOutlined />, label: '已发布短剧' },
  { key: '/content-promotion', icon: <NotificationOutlined />, label: '内容推广' },
  { key: '/publish', icon: <CloudUploadOutlined />, label: '发布中心' },
  { key: '/accounts', icon: <UserSwitchOutlined />, label: '平台账号' },
  { key: '/model-settings', icon: <RobotOutlined />, label: '大模型配置' },
];

export function WorkspaceLayout({ health, title, subtitle, actions, children }: WorkspaceLayoutProps) {
  const location = useLocation();
  const selectedKey = location.pathname.startsWith('/published')
    ? '/published'
    : location.pathname.startsWith('/content-promotion')
      ? '/content-promotion'
      : location.pathname.startsWith('/publish')
      ? '/publish'
      : location.pathname.startsWith('/accounts')
          ? '/accounts'
          : location.pathname.startsWith('/model-settings')
            ? '/model-settings'
          : '/';

  return (
    <Layout className="app-shell">
      <Sider width={300} className="app-sider" breakpoint="lg" collapsedWidth={0}>
        <AppSidebar />
        <div className="side-nav-block">
          <Text className="side-nav-label" type="secondary">
            功能菜单
          </Text>
          <Menu
            className="workspace-menu"
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => {
              if (key !== selectedKey) history.push(key);
            }}
          />
        </div>
        <div className="side-footer">
          <AppstoreOutlined />
          <Text type="secondary">剪辑服务和发布服务保持独立，通过 API 串联。</Text>
        </div>
      </Sider>
      <Layout>
        <Header className="app-header">
          <div>
            <Title level={3} className="page-title">
              {title}
            </Title>
            {typeof subtitle === 'string' ? <Text type="secondary">{subtitle}</Text> : subtitle}
          </div>
          {actions}
        </Header>
        <Content className="app-content">{children}</Content>
      </Layout>
    </Layout>
  );
}
