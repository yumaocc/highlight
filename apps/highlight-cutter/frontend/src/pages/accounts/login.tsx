import { ArrowLeftOutlined, LoginOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Tag, Typography } from 'antd';
import { history, useSearchParams } from '@umijs/max';
import { useEffect, useRef, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { getHealth } from '@/services/api';
import { fallbackPlatforms, startAccountLogin, type AccountLoginEvent } from '@/services/publish';
import type { Health } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Text, Paragraph } = Typography;

type LoginFormValues = {
  platform: string;
  accountName: string;
};

type LogLine = {
  id: number;
  type: AccountLoginEvent['type'];
  message: string;
};

export default function AccountLoginPage() {
  const [params] = useSearchParams();
  const [form] = Form.useForm<LoginFormValues>();
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
  const [qrcodeUrl, setQrcodeUrl] = useState('');
  const [logs, setLogs] = useState<LogLine[]>([]);
  const closeLoginRef = useRef<null | (() => void)>(null);
  const logIdRef = useRef(0);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
    form.setFieldsValue({
      platform: params.get('platform') || 'douyin',
      accountName: params.get('accountName') || '',
    });
    return () => stopLogin();
  }, []);

  function appendLog(type: AccountLoginEvent['type'], message: string) {
    logIdRef.current += 1;
    setLogs((current) => [...current, { id: logIdRef.current, type, message }]);
  }

  function stopLogin() {
    closeLoginRef.current?.();
    closeLoginRef.current = null;
  }

  function handleStop() {
    stopLogin();
    setStatus('idle');
    appendLog('status', '已断开登录流，后端会终止对应登录子进程。');
  }

  async function restartLogin() {
    const values = await form.validateFields();
    startLogin(values);
  }

  function startLogin(values: LoginFormValues) {
    stopLogin();
    setStatus('running');
    setQrcodeUrl('');
    setLogs([]);
    appendLog('status', `准备登录 ${values.platform} / ${values.accountName}`);
    try {
      closeLoginRef.current = startAccountLogin(values, (event) => {
        if (event.type === 'qrcode') {
          setQrcodeUrl(event.imageUrl);
          appendLog('qrcode', '已获取二维码，请扫码确认登录。');
          return;
        }
        appendLog(event.type, event.message);
        if (event.type === 'success') {
          setStatus('success');
          stopLogin();
        }
        if (event.type === 'error') {
          setStatus('error');
          stopLogin();
        }
      });
    } catch (error) {
      setStatus('error');
      appendLog('error', getErrorMessage(error));
    }
  }

  const statusColor = status === 'success' ? 'success' : status === 'error' ? 'error' : status === 'running' ? 'processing' : 'default';

  return (
    <WorkspaceLayout
      health={health}
      title="账号登录"
      subtitle="独立登录页会保留 social-auto-upload 子进程的完整输出，方便排查二维码、浏览器和平台风控问题。"
      actions={
        <Space>
          <Tag color={statusColor}>{status}</Tag>
          <Button icon={<ArrowLeftOutlined />} onClick={() => history.push('/accounts')}>
            返回账号
          </Button>
        </Space>
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="登录参数">
            <Form form={form} layout="vertical" onFinish={startLogin}>
              <Form.Item name="platform" label="平台" rules={[{ required: true, message: '请选择平台' }]}>
                <Select
                  options={fallbackPlatforms
                    .filter((platform) => ['douyin', 'xiaohongshu', 'kuaishou', 'wechat_channels', 'bilibili', 'youtube'].includes(platform.key))
                    .map((platform) => ({ value: platform.key, label: platform.name }))}
                />
              </Form.Item>
              <Form.Item name="accountName" label="账号备注名" rules={[{ required: true, message: '请输入账号备注名' }]}>
                <Input placeholder="例如：main 或 抖音主号" />
              </Form.Item>
              <Space wrap>
                <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={status === 'running'}>
                  开始登录
                </Button>
                <Button icon={<StopOutlined />} disabled={status !== 'running'} onClick={handleStop}>
                  停止
                </Button>
                <Button icon={<ReloadOutlined />} onClick={restartLogin}>
                  重新开始
                </Button>
              </Space>
            </Form>
          </Card>

          <Card title="二维码" className="login-side-card">
            {qrcodeUrl ? (
              <img className="login-qrcode-large" src={qrcodeUrl} alt="平台登录二维码" />
            ) : (
              <Alert type="info" showIcon message="等待子进程输出二维码" description="如果平台打开了有头浏览器，也可以直接在浏览器窗口里扫码。" />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          <Card title="终端输出">
            <div className="login-terminal">
              {logs.length ? (
                logs.map((line) => (
                  <div key={line.id} className={`login-terminal-line login-terminal-${line.type}`}>
                    <Text className="login-terminal-prefix">[{line.type}]</Text>
                    <span>{line.message}</span>
                  </div>
                ))
              ) : (
                <Paragraph className="compact-paragraph">
                  <Text type="secondary">点击开始登录后，这里会显示后端 SSE 和 sau_cli.py 子进程输出。</Text>
                </Paragraph>
              )}
            </div>
          </Card>
        </Col>
      </Row>
    </WorkspaceLayout>
  );
}
