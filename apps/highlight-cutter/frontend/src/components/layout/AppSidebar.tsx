import { Typography } from 'antd';

const { Text, Title } = Typography;

export function AppSidebar() {
  return (
    <div className="brand-block">
      <div className="brand-mark">HC</div>
      <div>
        <Title level={4} className="brand-title">
          高光剪辑
        </Title>
        <Text type="secondary">本地视频处理</Text>
      </div>
    </div>
  );
}
