import {
  ApiOutlined,
  AudioOutlined,
  EyeOutlined,
  PictureOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { getHealth, getModelSettings, updateModelSettings } from '@/services/api';
import type { Health, ModelSettings, ModelSettingsUpdate, ModelUsageNode } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Text } = Typography;

type FormValues = ModelSettingsUpdate;

const providerMeta = {
  openai: { label: 'OpenAI', color: 'green' },
  gemini: { label: 'Gemini', color: 'blue' },
  dynamic: { label: '可切换', color: 'gold' },
} as const;

const stageIcons: Record<string, React.ReactNode> = {
  '素材理解': <AudioOutlined />,
  '视觉复核': <EyeOutlined />,
  '剪辑决策': <ApiOutlined />,
  '内容生成': <PictureOutlined />,
};

function toFormValues(settings: ModelSettings): FormValues {
  return {
    openai_api_key: '',
    clear_openai_api_key: false,
    openai_base_url: settings.openai.base_url,
    openai_text_model: settings.openai.text_model,
    openai_image_model: settings.openai.image_model,
    openai_wire_api: settings.openai.wire_api,
    openai_transcribe_model: settings.openai.transcribe_model,
    gemini_api_key: '',
    clear_gemini_api_key: false,
    gemini_base_url: settings.gemini.base_url,
    gemini_model: settings.gemini.model,
    gemini_tts_model: settings.gemini.tts_model,
    gemini_tts_voice: settings.gemini.tts_voice,
    gemini_api_style: settings.gemini.api_style,
    transcribe_provider: settings.transcribe_provider,
  };
}

export default function ModelSettingsPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const [health, setHealth] = useState<Health | null>(null);
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const transcribeProvider = Form.useWatch('transcribe_provider', form);

  async function load() {
    setLoading(true);
    try {
      const [nextSettings, nextHealth] = await Promise.all([getModelSettings(), getHealth().catch(() => null)]);
      setSettings(nextSettings);
      setHealth(nextHealth);
      form.setFieldsValue(toFormValues(nextSettings));
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function save(values: FormValues) {
    setSaving(true);
    try {
      const next = await updateModelSettings(values);
      setSettings(next);
      form.setFieldsValue(toFormValues(next));
      message.success('大模型配置已生效');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  const nodes = useMemo(() => settings?.usage_nodes || [], [settings]);
  const currentModel = (node: ModelUsageNode) => {
    if (!settings) return '-';
    if (node.key === 'transcription') {
      return settings.transcribe_provider === 'openai'
        ? settings.openai.transcribe_model
        : settings.gemini.model;
    }
    const models: Record<string, string> = {
      openai_text_model: settings.openai.text_model,
      openai_image_model: settings.openai.image_model,
      gemini_model: settings.gemini.model,
      gemini_tts_model: settings.gemini.tts_model,
    };
    return models[node.model_field] || '-';
  };

  return (
    <WorkspaceLayout
      health={health}
      title="大模型配置"
      subtitle="管理模型提供方、调用协议和各业务节点的实际模型。"
      actions={
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>
          重新读取
        </Button>
      }
    >
      <Form form={form} layout="vertical" onFinish={save} requiredMark={false}>
        <Alert
          type="info"
          showIcon
          message="API Key 只写不读"
          description="已保存的密钥不会显示在页面中。留空会保留原密钥，仅在输入新值或勾选清除时更改。"
          className="model-settings-alert"
        />

        <Row gutter={[16, 16]}>
          <Col xs={24} xl={12}>
            <Card
              title={<Space><ApiOutlined />OpenAI</Space>}
              extra={<Tag color={settings?.openai.api_key_configured ? 'success' : 'warning'}>{settings?.openai.api_key_configured ? '密钥已配置' : '未配置密钥'}</Tag>}
            >
              <Form.Item name="openai_api_key" label="API Key">
                <Input.Password autoComplete="new-password" placeholder={settings?.openai.api_key_configured ? '留空保留已有密钥' : '输入 API Key'} />
              </Form.Item>
              {settings?.openai.api_key_configured && <Form.Item name="clear_openai_api_key" valuePropName="checked"><Checkbox>清除已保存的 OpenAI 密钥</Checkbox></Form.Item>}
              <Form.Item name="openai_base_url" label="Base URL">
                <Input placeholder="https://api.openai.com" />
              </Form.Item>
              <Row gutter={12}>
                <Col xs={24} md={12}><Form.Item name="openai_text_model" label="文本模型" rules={[{ required: true }]}><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="openai_image_model" label="图片模型" rules={[{ required: true }]}><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="openai_transcribe_model" label="转写模型" rules={[{ required: true }]}><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="openai_wire_api" label="文本调用协议"><Select options={[{ value: 'responses', label: 'Responses API' }, { value: 'chat_completions', label: 'Chat Completions' }]} /></Form.Item></Col>
              </Row>
            </Card>
          </Col>

          <Col xs={24} xl={12}>
            <Card
              title={<Space><EyeOutlined />Gemini</Space>}
              extra={<Tag color={settings?.gemini.api_key_configured ? 'success' : 'warning'}>{settings?.gemini.api_key_configured ? '密钥已配置' : '未配置密钥'}</Tag>}
            >
              <Form.Item name="gemini_api_key" label="API Key">
                <Input.Password autoComplete="new-password" placeholder={settings?.gemini.api_key_configured ? '留空保留已有密钥' : '输入 API Key'} />
              </Form.Item>
              {settings?.gemini.api_key_configured && <Form.Item name="clear_gemini_api_key" valuePropName="checked"><Checkbox>清除已保存的 Gemini 密钥</Checkbox></Form.Item>}
              <Form.Item name="gemini_base_url" label="Base URL">
                <Input placeholder="https://generativelanguage.googleapis.com" />
              </Form.Item>
              <Row gutter={12}>
                <Col xs={24} md={12}><Form.Item name="gemini_model" label="理解 / 复核模型" rules={[{ required: true }]}><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="gemini_tts_model" label="TTS 模型" rules={[{ required: true }]}><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="gemini_tts_voice" label="TTS 音色" rules={[{ required: true }]}><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="gemini_api_style" label="视觉调用方式"><Select options={[{ value: 'native', label: 'Gemini Native' }, { value: 'openai', label: 'OpenAI 兼容' }]} /></Form.Item></Col>
              </Row>
            </Card>
          </Col>
        </Row>

        <Card title={<Space><AudioOutlined />转写提供方</Space>} className="model-transcribe-card">
          <Form.Item name="transcribe_provider" noStyle>
            <Select style={{ width: 280 }} options={[{ value: 'gemini', label: 'Gemini 音频理解' }, { value: 'openai', label: 'OpenAI 音频转写' }]} />
          </Form.Item>
          <Text type="secondary" className="model-transcribe-note">
            当前使用 {transcribeProvider === 'openai' ? 'OpenAI 转写模型' : 'Gemini 理解 / 复核模型'}处理音频。
          </Text>
        </Card>

        <Card title="大模型使用节点" className="model-node-card">
          <Table
            rowKey="key"
            loading={loading}
            dataSource={nodes}
            pagination={false}
            size="middle"
            columns={[
              { title: '阶段', dataIndex: 'stage', width: 140, render: (value) => <Space>{stageIcons[value]}<Text>{value}</Text></Space> },
              { title: '节点', dataIndex: 'name', width: 180, render: (value, record) => <Space direction="vertical" size={0}><Text strong>{value}</Text><Text type="secondary">{record.description}</Text></Space> },
              { title: '提供方', dataIndex: 'provider', width: 110, render: (value: keyof typeof providerMeta) => <Tag color={providerMeta[value].color}>{providerMeta[value].label}</Tag> },
              { title: '当前模型', key: 'model', width: 220, render: (_, record) => <Text code>{currentModel(record)}</Text> },
            ]}
            scroll={{ x: 760 }}
          />
        </Card>

        <div className="model-settings-actions">
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving} size="large">
            保存并立即生效
          </Button>
        </div>
      </Form>
    </WorkspaceLayout>
  );
}
