import {
  App,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useEffect, useMemo, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { getHealth } from '@/services/api';
import {
  createPromptConfig,
  deletePromptConfig,
  getPromptConfigs,
  updatePromptConfig,
  type PromptConfig,
  type PromptConfigPayload,
} from '@/services/prompts';
import type { Health } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Paragraph, Text } = Typography;

type PromptFormValues = PromptConfigPayload;

const defaultPromptValues: PromptFormValues = {
  key: '',
  name: '',
  category: 'video_generation',
  description: '',
  content: '',
  enabled: true,
};

export default function SettingsPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<PromptFormValues>();
  const [health, setHealth] = useState<Health | null>(null);
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<PromptConfig | null>(null);
  const [keyword, setKeyword] = useState('');

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
    loadPrompts();
  }, []);

  const filteredPrompts = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    if (!query) return prompts;
    return prompts.filter((item) =>
      [item.key, item.name, item.description, item.content]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    );
  }, [keyword, prompts]);

  async function loadPrompts() {
    setLoading(true);
    try {
      setPrompts(await getPromptConfigs());
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function openCreateDrawer() {
    setEditingPrompt(null);
    form.setFieldsValue(defaultPromptValues);
    setDrawerOpen(true);
  }

  function openEditDrawer(prompt: PromptConfig) {
    setEditingPrompt(prompt);
    form.setFieldsValue({
      key: prompt.key,
      name: prompt.name,
      category: prompt.category,
      description: prompt.description,
      content: prompt.content,
      enabled: prompt.enabled,
    });
    setDrawerOpen(true);
  }

  async function submit(values: PromptFormValues) {
    setSaving(true);
    try {
      if (editingPrompt) {
        const updated = await updatePromptConfig(editingPrompt.id, {
          name: values.name,
          category: values.category,
          description: values.description,
          content: values.content,
          enabled: values.enabled,
        });
        setPrompts((items) => items.map((item) => (item.id === updated.id ? updated : item)));
        message.success('提示词已更新');
      } else {
        const created = await createPromptConfig(values);
        setPrompts((items) => [...items, created]);
        message.success('提示词已新增');
      }
      setDrawerOpen(false);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  }

  async function toggleEnabled(prompt: PromptConfig, enabled: boolean) {
    try {
      const updated = await updatePromptConfig(prompt.id, { enabled });
      setPrompts((items) => items.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  async function removePrompt(prompt: PromptConfig) {
    try {
      await deletePromptConfig(prompt.id);
      setPrompts((items) => items.filter((item) => item.id !== prompt.id));
      message.success('提示词已删除');
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  return (
    <WorkspaceLayout
      health={health}
      title="系统设置"
      subtitle="配置视频生成链路使用的模型提示词。"
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadPrompts} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
            新增提示词
          </Button>
        </Space>
      }
    >
      <Card title="提示词配置">
        <Space direction="vertical" size={16} className="full-width">
          <Input.Search
            allowClear
            placeholder="搜索 key、名称、说明或提示词内容"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <Table
            rowKey="id"
            loading={loading}
            dataSource={filteredPrompts}
            pagination={{ pageSize: 8, showSizeChanger: false }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无提示词配置" /> }}
            columns={[
              {
                title: '提示词',
                dataIndex: 'name',
                render: (_, record) => (
                  <Space direction="vertical" size={4}>
                    <Space wrap>
                      <Text strong>{record.name}</Text>
                      <Tag>{record.key}</Tag>
                      {record.is_system && <Tag color="blue">系统内置</Tag>}
                      <Tag color={record.enabled ? 'success' : 'default'}>{record.enabled ? '启用' : '停用'}</Tag>
                    </Space>
                    <Text type="secondary">{record.description || '未填写说明'}</Text>
                  </Space>
                ),
              },
              {
                title: '内容预览',
                dataIndex: 'content',
                responsive: ['md'],
                render: (value: string) => (
                  <Paragraph className="compact-paragraph" ellipsis={{ rows: 3 }}>
                    {value}
                  </Paragraph>
                ),
              },
              {
                title: '启用',
                width: 92,
                render: (_, record) => (
                  <Switch checked={record.enabled} onChange={(checked) => toggleEnabled(record, checked)} />
                ),
              },
              {
                title: '操作',
                width: 150,
                render: (_, record) => (
                  <Space>
                    <Button icon={<EditOutlined />} onClick={() => openEditDrawer(record)}>
                      编辑
                    </Button>
                    {!record.is_system && (
                      <Popconfirm
                        title="删除提示词？"
                        description="删除后无法用于后续生成。"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => removePrompt(record)}
                      >
                        <Button danger>删除</Button>
                      </Popconfirm>
                    )}
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      </Card>

      <Drawer
        title={editingPrompt ? '编辑提示词' : '新增提示词'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={defaultPromptValues} onFinish={submit}>
          <Form.Item
            name="key"
            label="Key"
            rules={[
              { required: true, message: '请输入 key' },
              { pattern: /^[a-zA-Z0-9_.-]+$/, message: '只支持字母、数字、下划线、点和短横线' },
            ]}
          >
            <Input disabled={Boolean(editingPrompt)} placeholder="promo_custom_style" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="例如：推广剪辑风格" />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true, message: '请输入分类' }]}>
            <Input placeholder="video_generation" />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={2} placeholder="这个提示词会影响哪一步生成" />
          </Form.Item>
          <Form.Item name="content" label="提示词内容" rules={[{ required: true, message: '请输入提示词内容' }]}>
            <Input.TextArea rows={12} placeholder="输入给模型的业务要求、剪辑策略或输出偏好" />
          </Form.Item>
          <Form.Item name="enabled" label="状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
          <Space className="form-actions">
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" htmlType="submit" loading={saving}>
              保存
            </Button>
          </Space>
        </Form>
      </Drawer>
    </WorkspaceLayout>
  );
}
