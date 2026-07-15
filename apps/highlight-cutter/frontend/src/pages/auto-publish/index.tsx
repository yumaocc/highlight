import { App, Button, Card, Checkbox, Form, Input, InputNumber, List, Progress, Select, Space, Steps, Tag, Typography } from 'antd';
import { CheckCircleOutlined, DeleteOutlined, LoadingOutlined, PlusOutlined, PlayCircleOutlined, RedoOutlined, SendOutlined } from '@ant-design/icons';
import { useEffect, useMemo, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import {
  checkAutoPublishRecord,
  createAutoPublishTask,
  getAutoPublishTask,
  getHealth,
  retryAutoPublishItem,
} from '@/services/api';
import { fallbackPlatforms, getPublishAccounts, type PublishAccount } from '@/services/publish';
import type { AutoPublishTask, Health } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Text, Paragraph } = Typography;

type AutoPublishFormValues = {
  names: string[];
  episodeLimit: number;
  publishEnabled: boolean;
  platform: string;
  accountIds: string[];
  kuaishouEnablePromotionTask: boolean;
  maxConcurrency: number;
};

const defaultValues: AutoPublishFormValues = {
  names: [''],
  episodeLimit: 5,
  publishEnabled: true,
  platform: 'kuaishou',
  accountIds: [],
  kuaishouEnablePromotionTask: true,
  maxConcurrency: 2,
};

export default function AutoPublishPage() {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm<AutoPublishFormValues>();
  const [health, setHealth] = useState<Health | null>(null);
  const [accounts, setAccounts] = useState<PublishAccount[]>([]);
  const [task, setTask] = useState<AutoPublishTask | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retryingIndex, setRetryingIndex] = useState<number | null>(null);

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    const selectedAccountIds = form.getFieldValue('accountIds') || [];
    const validIds = new Set(filteredAccounts.map((account) => String(account.id)));
    const hasValidSelection = selectedAccountIds.some((id: string) => validIds.has(String(id)));
    if (!filteredAccounts.length || hasValidSelection) return;
    form.setFieldValue('accountIds', filteredAccounts.map((account) => String(account.id)));
  }, [filteredAccounts, form]);

  useEffect(() => {
    if (!task?.id || !isActive(task.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await getAutoPublishTask(task.id);
        setTask(next);
        if (!isActive(next.status)) {
          message.success(next.message || '自动流程已完成');
        }
      } catch (error) {
        message.error(getErrorMessage(error));
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [task?.id, task?.status]);

  const publishEnabled = Form.useWatch('publishEnabled', form);
  const selectedPlatform = Form.useWatch('platform', form) || defaultValues.platform;
  const filteredAccounts = useMemo(
    () => accounts.filter((account) => account.platform === selectedPlatform),
    [accounts, selectedPlatform],
  );
  const currentStep = task ? (isActive(task.status) ? 2 : 3) : 0;

  async function loadInitialData() {
    try {
      const [nextHealth, nextAccounts] = await Promise.all([
        getHealth().catch(() => null),
        getPublishAccounts().catch(() => []),
      ]);
      setHealth(nextHealth);
      setAccounts(nextAccounts);
      const defaultAccountIds = nextAccounts
        .filter((account) => account.platform === defaultValues.platform)
        .map((account) => String(account.id));
      form.setFieldsValue({
        publishEnabled: true,
        platform: defaultValues.platform,
        accountIds: defaultAccountIds,
        kuaishouEnablePromotionTask: true,
      });
    } catch {
      setAccounts([]);
    }
  }

  function normalizeNames(value: string[] = []) {
    const seen = new Set<string>();
    return value
      .map((item) => item.trim())
      .filter((item) => {
        const key = item.replace(/\s+/g, '').toLowerCase();
        if (!item || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }

  async function submit(values: AutoPublishFormValues) {
    const names = normalizeNames(values.names);
    if (!names.length) {
      message.error('请至少添加一个短剧名称');
      return;
    }
    setSubmitting(true);
    try {
      const checks = await Promise.all(names.map((name) => checkAutoPublishRecord(name).catch(() => ({ exists: false }))));
      const duplicates = names.filter((_, index) => checks[index]?.exists);
      if (duplicates.length) {
        const confirmed = await new Promise<boolean>((resolve) => {
          modal.confirm({
            title: '发现已发布短剧',
            content: `以下名称已发布过：${duplicates.join('、')}。继续会自动跳过这些名称。`,
            okText: '继续',
            cancelText: '返回修改',
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          });
        });
        if (!confirmed) return;
      }
      const nextTask = await createAutoPublishTask({
        drama_names: names,
        episode_limit: values.episodeLimit,
        publish_enabled: Boolean(values.publishEnabled),
        platform: values.platform,
        account_ids: values.accountIds || [],
        kuaishou_enable_promotion_task: values.platform === 'kuaishou' ? Boolean(values.kuaishouEnablePromotionTask) : undefined,
        skip_existing: true,
        max_concurrency: values.maxConcurrency,
      });
      setTask(nextTask);
      message.success('自动流程已启动');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function retryItem(itemIndex: number) {
    if (!task) return;
    setRetryingIndex(itemIndex);
    try {
      const nextTask = await retryAutoPublishItem(task.id, itemIndex);
      setTask(nextTask);
      message.success('已从失败阶段继续执行');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setRetryingIndex(null);
    }
  }

  return (
    <WorkspaceLayout
      health={health}
      title="自动发布"
      subtitle={<Text type="secondary">批量输入短剧名称，自动查资源、下载前五集、剪辑并发布。</Text>}
    >
      <Space direction="vertical" size={16} className="full-width auto-publish-page">
        <Card>
          <Steps
            current={currentStep}
            items={[
              { title: '添加名称', icon: <PlayCircleOutlined /> },
              { title: '确认配置', icon: <CheckCircleOutlined /> },
              { title: '自动执行', icon: isActive(task?.status || '') ? <LoadingOutlined /> : <SendOutlined /> },
              { title: '记录状态', icon: <CheckCircleOutlined /> },
            ]}
          />
        </Card>

        <Card title="批量任务">
          <Form form={form} layout="vertical" initialValues={defaultValues} onFinish={submit}>
            <Form.List name="names">
              {(fields, { add, remove }) => (
                <Form.Item label="短剧名称" required>
                  <Space direction="vertical" size={8} className="full-width">
                    {fields.map((field, index) => (
                      <Space.Compact key={field.key} className="auto-publish-name-row">
                        <Form.Item
                          {...field}
                          noStyle
                          rules={[{ required: true, whitespace: true, message: '请输入短剧名称' }]}
                        >
                          <Input placeholder={`短剧名称 ${index + 1}`} />
                        </Form.Item>
                        <Button
                          aria-label="删除短剧名称"
                          icon={<DeleteOutlined />}
                          disabled={fields.length === 1}
                          onClick={() => remove(field.name)}
                        />
                      </Space.Compact>
                    ))}
                    <Button type="dashed" icon={<PlusOutlined />} onClick={() => add('')}>
                      增加短剧
                    </Button>
                  </Space>
                </Form.Item>
              )}
            </Form.List>
            <Space size={12} wrap className="full-width">
              <Form.Item name="episodeLimit" label="下载集数">
                <InputNumber min={1} max={50} />
              </Form.Item>
              <Form.Item
                name="maxConcurrency"
                label="并发数"
                tooltip="同时处理的短剧数量。发布会打开浏览器并占用本机资源，建议 2 起步。"
              >
                <InputNumber min={1} max={4} />
              </Form.Item>
            </Space>
            <Paragraph type="secondary">
              系统会从青雀匹配百度分享链接，用 BaiduPCS-Go 转存到网盘后下载剧情前几集。
            </Paragraph>
            <Form.Item name="publishEnabled" valuePropName="checked">
              <Checkbox>剪辑完成后自动发布</Checkbox>
            </Form.Item>
            {publishEnabled && (
              <Space size={12} wrap className="full-width">
                <Form.Item name="platform" label="平台">
                  <Select options={fallbackPlatforms.map((platform) => ({ value: platform.key, label: platform.name }))} />
                </Form.Item>
                <Form.Item name="accountIds" label="账号" rules={[{ required: true, message: '请选择发布账号' }]}>
                  <Select
                    mode="multiple"
                    options={filteredAccounts.map((account) => ({ value: String(account.id), label: account.name }))}
                    placeholder="选择账号"
                    style={{ minWidth: 220 }}
                  />
                </Form.Item>
                {selectedPlatform === 'kuaishou' && (
                  <Form.Item name="kuaishouEnablePromotionTask" valuePropName="checked">
                    <Checkbox>关联快手变现任务</Checkbox>
                  </Form.Item>
                )}
              </Space>
            )}
            <Button type="primary" htmlType="submit" loading={submitting} icon={<PlayCircleOutlined />}>
              开始自动执行
            </Button>
          </Form>
        </Card>

        {task && (
          <Card title="执行进度">
            <Space direction="vertical" size={12} className="full-width">
              <Progress percent={task.progress || 0} status={task.status === 'failed' ? 'exception' : isActive(task.status) ? 'active' : 'success'} />
              <Text>{task.message}</Text>
              <List
                dataSource={task.items}
                renderItem={(item, itemIndex) => (
                  <List.Item
                    actions={item.status === 'failed' ? [
                      <Button
                        key="retry"
                        icon={<RedoOutlined />}
                        loading={retryingIndex === itemIndex}
                        onClick={() => retryItem(itemIndex)}
                      >
                        从失败处重试
                      </Button>,
                    ] : undefined}
                  >
                    <Space direction="vertical" size={6} className="full-width">
                      <Space wrap>
                        <Text strong>{item.name}</Text>
                        <Tag color={statusColor(item.status)}>{statusLabel(item.status)}</Tag>
                        {item.remote_dir && <Tag>{item.remote_dir}</Tag>}
                      </Space>
                      <Progress percent={item.progress || 0} size="small" />
                      <Text type={item.status === 'failed' ? 'danger' : 'secondary'}>{item.message}</Text>
                      {item.resource && <Text type="secondary">资源：{item.resource.baidu_url} {item.resource.extract_code ? `提取码 ${item.resource.extract_code}` : ''}</Text>}
                      {item.timings && Object.keys(item.timings).length > 0 && (
                        <Space size={6} wrap>
                          {item.duration_display && <Tag color="purple">总耗时 {item.duration_display}</Tag>}
                          {Object.entries(item.timings).map(([key, timing]) => (
                            <Tag key={key}>{timing.label} {timing.display}</Tag>
                          ))}
                        </Space>
                      )}
                    </Space>
                  </List.Item>
                )}
              />
            </Space>
          </Card>
        )}

      </Space>
    </WorkspaceLayout>
  );
}

function isActive(status: string) {
  return status === 'pending' || status === 'running';
}

function statusColor(status: string) {
  if (status === 'succeeded') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'skipped') return 'orange';
  if (status === 'running') return 'blue';
  return 'default';
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '等待中',
    running: '执行中',
    succeeded: '完成',
    failed: '失败',
    skipped: '已跳过',
  };
  return labels[status] || status;
}
