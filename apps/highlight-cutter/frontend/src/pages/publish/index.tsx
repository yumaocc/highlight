import {
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Form,
  Input,
  List,
  Progress,
  Row,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd';
import { CloudUploadOutlined, FolderOpenOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { getHealth, getProjectAssets, getProjects } from '@/services/api';
import {
  createPublishTask,
  fallbackAccounts,
  fallbackPlatforms,
  getPublishAccounts,
  getPublishPlatforms,
  getPublishTasks,
  type PublishAccount,
  type PublishPlatform,
  type PublishTask,
} from '@/services/publish';
import type { GeneratedAsset, Health, Project } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Text, Paragraph } = Typography;
const DEFAULT_PUBLISH_TAGS = ['#快来看短剧', '#AI创想家计划', '#神仙剪刀手'];

type PublishFormValues = {
  platform: string;
  accountIds: Array<string | number>;
  filePaths?: string;
  title: string;
  description?: string;
  topics?: string;
  isOriginal?: boolean;
  scheduleEnabled?: boolean;
  scheduleAt?: string;
  kuaishouEnablePromotionTask?: boolean;
  kuaishouPromotionTaskTitle?: string;
  projectId?: number;
  assetIds?: number[];
};

type PublishTab = {
  key: string;
  label: string;
  files: UploadFile[];
};

const defaultValues: PublishFormValues = {
  platform: 'douyin',
  accountIds: [],
  title: '',
  description: '',
  topics: DEFAULT_PUBLISH_TAGS.join(' '),
  isOriginal: true,
  scheduleEnabled: false,
  kuaishouEnablePromotionTask: true,
};

export default function PublishPage() {
  const { message } = App.useApp();
  const [health, setHealth] = useState<Health | null>(null);
  const [platforms, setPlatforms] = useState<PublishPlatform[]>(fallbackPlatforms);
  const [accounts, setAccounts] = useState<PublishAccount[]>(fallbackAccounts);
  const [tasks, setTasks] = useState<PublishTask[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [assets, setAssets] = useState<GeneratedAsset[]>([]);
  const [serviceReady, setServiceReady] = useState(false);
  const [activeKey, setActiveKey] = useState('publish-1');
  const [tabs, setTabs] = useState<PublishTab[]>([{ key: 'publish-1', label: '发布 1', files: [] }]);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<PublishFormValues>();

  useEffect(() => {
    loadHighlightHealth();
    loadProjectData();
    loadPublishData();
  }, []);

  useEffect(() => {
    const hasActiveTask = tasks.some((task) => isActivePublishTask(task.status));
    if (!serviceReady || !hasActiveTask) return;
    const timer = window.setInterval(() => {
      loadPublishData();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [serviceReady, tasks]);

  const activeTab = tabs.find((item) => item.key === activeKey) || tabs[0];
  const selectedPlatform = Form.useWatch('platform', form) || defaultValues.platform;
  const enableKuaishouPromotionTask = Form.useWatch('kuaishouEnablePromotionTask', form);
  const selectedProjectId = Form.useWatch('projectId', form);
  const filteredAccounts = useMemo(
    () => accounts.filter((account) => account.platform === selectedPlatform),
    [accounts, selectedPlatform],
  );

  useEffect(() => {
    if (!selectedProjectId) {
      setAssets([]);
      return;
    }
    loadAssets(selectedProjectId);
  }, [selectedProjectId]);

  async function loadHighlightHealth() {
    try {
      setHealth(await getHealth());
    } catch {
      setHealth(null);
    }
  }

  async function loadPublishData() {
    try {
      const [nextPlatforms, nextAccounts, nextTasks] = await Promise.all([
        getPublishPlatforms(),
        getPublishAccounts(),
        getPublishTasks(),
      ]);
      setPlatforms(nextPlatforms.length ? nextPlatforms : fallbackPlatforms);
      setAccounts(nextAccounts);
      setTasks(nextTasks);
      setServiceReady(true);
    } catch {
      setPlatforms(fallbackPlatforms);
      setAccounts(fallbackAccounts);
      setTasks([]);
      setServiceReady(false);
    }
  }

  async function loadProjectData() {
    try {
      const nextProjects = await getProjects();
      setProjects(nextProjects);
      const params = new URLSearchParams(window.location.search);
      const queryProjectId = Number(params.get('projectId') || 0);
      if (queryProjectId) {
        form.setFieldValue('projectId', queryProjectId);
      } else if (nextProjects.length && !form.getFieldValue('projectId')) {
        form.setFieldValue('projectId', nextProjects[0].id);
      }
    } catch {
      setProjects([]);
    }
  }

  async function loadAssets(projectId: number) {
    try {
      const nextAssets = await getProjectAssets(projectId);
      setAssets(nextAssets);
      const params = new URLSearchParams(window.location.search);
      const assetIds = (params.get('assetIds') || '')
        .split(',')
        .map((item) => Number(item))
        .filter(Boolean);
      if (assetIds.length) {
        const selectedAssets = nextAssets.filter((asset) => assetIds.includes(asset.id));
        form.setFieldsValue(buildPublishDefaults(selectedAssets, projectId));
      }
    } catch {
      setAssets([]);
    }
  }

  function addTab() {
    const index = tabs.length + 1;
    const next = { key: `publish-${Date.now()}`, label: `发布 ${index}`, files: [] };
    setTabs([...tabs, next]);
    setActiveKey(next.key);
    form.resetFields();
    form.setFieldsValue({ ...defaultValues });
  }

  function removeTab(targetKey: string) {
    const nextTabs = tabs.filter((item) => item.key !== targetKey);
    if (!nextTabs.length) return;
    setTabs(nextTabs);
    if (activeKey === targetKey) setActiveKey(nextTabs[0].key);
  }

  function updateActiveFiles(files: UploadFile[]) {
    setTabs((items) => items.map((item) => (item.key === activeKey ? { ...item, files } : item)));
  }

  function updateSelectedAssets(assetIds: number[]) {
    const selectedAssets = assets.filter((asset) => assetIds.includes(asset.id));
    form.setFieldsValue(buildPublishDefaults(selectedAssets, form.getFieldValue('projectId')));
  }

  function buildPublishDefaults(selectedAssets: GeneratedAsset[], projectId?: number) {
    const firstAsset = selectedAssets[0];
    const projectName =
      projects.find((project) => project.id === (projectId || firstAsset?.project_id))?.name ||
      cleanInternalAssetTitle(firstAsset?.title || '');
    return {
      assetIds: selectedAssets.map((asset) => asset.id),
      filePaths: selectedAssets.map((asset) => asset.output_path).filter(Boolean).join('\n'),
      title: projectName,
      description: firstAsset ? getAssetPromoCopy(firstAsset) : '',
      topics: collectPublishTags(selectedAssets).join(' '),
    };
  }

  async function submit(values: PublishFormValues) {
    const filePaths = (values.filePaths || '')
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean);
    const localFiles = activeTab.files.map((file) => file.name);
    if (!filePaths.length && !localFiles.length) {
      message.error('请先选择本地文件，或填写剪辑服务生成的视频路径');
      return;
    }

    setSubmitting(true);
    try {
      const task = await createPublishTask({
        platform: values.platform,
        accountIds: values.accountIds,
        filePaths: filePaths.length ? filePaths : localFiles,
        title: values.title,
        description: values.description,
        topics: parsePublishTags(values.topics),
        isOriginal: Boolean(values.isOriginal),
        scheduleAt: values.scheduleEnabled ? values.scheduleAt : undefined,
        kuaishouEnablePromotionTask: selectedPlatform === 'kuaishou' ? Boolean(values.kuaishouEnablePromotionTask) : undefined,
        kuaishouPromotionTaskTitle:
          selectedPlatform === 'kuaishou' && values.kuaishouEnablePromotionTask
            ? values.kuaishouPromotionTaskTitle?.trim()
            : undefined,
      });
      setTasks([task, ...tasks]);
      message.success('发布任务已创建');
    } catch (error) {
      message.error(serviceReady ? getErrorMessage(error) : '发布服务还未接入，当前页面只完成前端入口和表单骨架');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <WorkspaceLayout
      health={health}
      title="发布中心"
      subtitle="把剪辑结果分发到多平台账号；发布服务接入后这里会创建真实上传任务。"
      actions={
        <Space>
          <Tag color={serviceReady ? 'success' : 'warning'}>{serviceReady ? '发布服务已连接' : '等待 publish-service'}</Tag>
          <Button icon={<PlusOutlined />} onClick={addTab}>
            新增发布
          </Button>
          <Button onClick={loadPublishData}>刷新</Button>
        </Space>
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card className="tool-card">
            <Tabs
              activeKey={activeKey}
              type="editable-card"
              items={tabs.map((item) => ({
                key: item.key,
                label: item.label,
                closable: tabs.length > 1,
                children: (
                  <Form form={form} layout="vertical" initialValues={defaultValues} onFinish={submit} className="publish-form">
                    <Row gutter={16}>
                      <Col xs={24} md={12}>
                        <Form.Item name="projectId" label="短剧项目">
                          <Select
                            placeholder="选择项目"
                            options={projects.map((project) => ({
                              value: project.id,
                              label: `${project.name} · ${project.asset_count || 0} 产物`,
                            }))}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={12}>
                        <Form.Item name="assetIds" label="项目资产">
                          <Select
                            mode="multiple"
                            placeholder="选择项目内生成的视频"
                            options={assets.map((asset) => ({
                              value: asset.id,
                              label: `${asset.title} · ${asset.type}`,
                            }))}
                            onChange={updateSelectedAssets}
                          />
                        </Form.Item>
                      </Col>
                    </Row>

                    <Row gutter={16}>
                      <Col xs={24} md={12}>
                        <Form.Item name="platform" label="平台" rules={[{ required: true, message: '请选择平台' }]}>
                          <Select
                            options={platforms.map((platform) => ({
                              value: platform.key,
                              label: platform.name,
                            }))}
                          />
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={12}>
                        <Form.Item name="accountIds" label="账号" rules={[{ required: true, message: '请选择账号' }]}>
                          <Select
                            mode="multiple"
                            placeholder="选择账号"
                            options={filteredAccounts.map((account) => ({
                              value: account.id,
                              label: `${account.name} · ${account.status}`,
                            }))}
                          />
                        </Form.Item>
                      </Col>
                    </Row>

                    <Form.Item label="视频文件">
                      <Upload.Dragger
                        multiple
                        beforeUpload={() => false}
                        fileList={item.files}
                        onChange={({ fileList }) => updateActiveFiles(fileList)}
                        accept="video/*"
                      >
                        <p className="ant-upload-drag-icon">
                          <CloudUploadOutlined />
                        </p>
                        <p className="ant-upload-text">拖入视频文件，或点击选择</p>
                        <p className="ant-upload-hint">当前阶段仅记录本地文件名；真实上传由 publish-service 接入后处理。</p>
                      </Upload.Dragger>
                    </Form.Item>

                    <Form.Item name="filePaths" label="剪辑结果路径">
                      <Input.TextArea
                        rows={3}
                        placeholder="/Users/q/Desktop/work/highlight/apps/highlight-service/outputs/promos/promo_latest.mp4"
                      />
                    </Form.Item>

                    <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
                      <Input.TextArea rows={2} maxLength={100} showCount placeholder="请输入发布标题" />
                    </Form.Item>

                    <Form.Item name="description" label="描述">
                      <Input.TextArea rows={4} maxLength={1000} showCount placeholder="请输入简介、卖点或剧情说明" />
                    </Form.Item>

                    <Form.Item name="topics" label="话题">
                      <Input placeholder="#快来看短剧 #AI创想家计划 #神仙剪刀手" />
                    </Form.Item>

                    <Row gutter={16}>
                      <Col xs={24} md={12}>
                        <Form.Item name="isOriginal" valuePropName="checked">
                          <Checkbox>声明原创</Checkbox>
                        </Form.Item>
                      </Col>
                      <Col xs={24} md={12}>
                        <Form.Item name="scheduleEnabled" valuePropName="checked">
                          <Checkbox>定时发布</Checkbox>
                        </Form.Item>
                      </Col>
                    </Row>

                    {selectedPlatform === 'kuaishou' && (
                      <Row gutter={16}>
                        <Col xs={24} md={12}>
                          <Form.Item name="kuaishouEnablePromotionTask" valuePropName="checked">
                            <Checkbox>关联快手变现任务</Checkbox>
                          </Form.Item>
                        </Col>
                        <Col xs={24} md={12}>
                          <Form.Item name="kuaishouPromotionTaskTitle" label="快手变现任务标题">
                            <Input disabled={!enableKuaishouPromotionTask} placeholder="默认使用发布标题匹配" />
                          </Form.Item>
                        </Col>
                      </Row>
                    )}

                    <Form.Item name="scheduleAt" label="定时时间">
                      <Input placeholder="2026-06-30 10:00" />
                    </Form.Item>

                    <Space className="form-actions">
                      <Button htmlType="button" onClick={() => form.resetFields()}>
                        清空
                      </Button>
                      <Button type="primary" htmlType="submit" icon={<SendOutlined />} loading={submitting}>
                        创建发布任务
                      </Button>
                    </Space>
                  </Form>
                ),
              }))}
              onChange={setActiveKey}
              onEdit={(targetKey, action) => {
                if (action === 'add') addTab();
                if (action === 'remove') removeTab(String(targetKey));
              }}
            />
          </Card>
        </Col>

        <Col xs={24} xl={9}>
          <Space direction="vertical" size={16} className="full-width">
            <Card title="账号状态" extra={<FolderOpenOutlined />}>
              <List
                dataSource={accounts}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无账号数据" /> }}
                renderItem={(account) => (
                  <List.Item>
                    <List.Item.Meta
                      title={
                        <Space>
                          <Text strong>{account.name}</Text>
                          <Tag>{account.platform}</Tag>
                        </Space>
                      }
                      description={account.remark || account.status}
                    />
                  </List.Item>
                )}
              />
            </Card>

            <Card title="发布任务">
              {tasks.length ? (
                <List
                  dataSource={tasks}
                  renderItem={(task) => (
                    <List.Item>
                      <List.Item.Meta
                        title={task.title}
                        description={
                          <Space direction="vertical" size={4}>
                            <Text type="secondary">
                              {task.platform} · {task.accountNames?.join(', ') || '未指定账号'}
                            </Text>
                            <Progress
                              percent={publishTaskProgress(task.status)}
                              status={task.status === 'failed' ? 'exception' : isActivePublishTask(task.status) ? 'active' : 'normal'}
                              size="small"
                            />
                            {task.message && <Paragraph className="compact-paragraph">{task.message}</Paragraph>}
                          </Space>
                        }
                      />
                      <Tag color={publishTaskTagColor(task.status)}>{publishTaskStatusText(task.status)}</Tag>
                    </List.Item>
                  )}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无发布任务" />
              )}
            </Card>
          </Space>
        </Col>
      </Row>
    </WorkspaceLayout>
  );
}

function collectPublishTags(assets: GeneratedAsset[]) {
  const tags = [...DEFAULT_PUBLISH_TAGS];
  assets.forEach((asset) => {
    const assetTags = asset.metadata?.publish_tags;
    if (Array.isArray(assetTags)) tags.push(...assetTags);
  });
  return normalizePublishTags(tags);
}

function getAssetPromoCopy(asset: GeneratedAsset) {
  const promoCopy = asset.metadata?.promo_copy;
  return typeof promoCopy === 'string' ? promoCopy.trim() : '';
}

function cleanInternalAssetTitle(title: string) {
  return String(title || '')
    .replace(/[\s_-]*(剧情精剪|剧情精简|精彩剪辑|高光切片|引流版本|引流版|推广版本|推广版|宣传版本|宣传版|短剧剪辑|剪辑版本|剪辑版|精剪版本|精剪版|精剪|切片)$/u, '')
    .trim();
}

function parsePublishTags(value?: string) {
  const rawTags = (value || '')
    .split(/[\s,，\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return normalizePublishTags(rawTags);
}

function normalizePublishTags(tags: string[]) {
  const normalized: string[] = [];
  tags.forEach((value) => {
    const text = String(value).trim().replace(/^#+/, '').trim();
    if (!text) return;
    const tag = `#${text}`;
    if (!normalized.includes(tag)) normalized.push(tag);
  });
  DEFAULT_PUBLISH_TAGS.slice().reverse().forEach((tag) => {
    if (!normalized.includes(tag)) normalized.unshift(tag);
  });
  return normalized;
}

function isActivePublishTask(status: PublishTask['status']) {
  return status === 'pending' || status === 'running';
}

function publishTaskProgress(status: PublishTask['status']) {
  if (status === 'succeeded') return 100;
  if (status === 'failed' || status === 'canceled') return 100;
  if (status === 'running') return 45;
  return 5;
}

function publishTaskTagColor(status: PublishTask['status']) {
  if (status === 'succeeded') return 'success';
  if (status === 'failed') return 'error';
  if (status === 'canceled') return 'default';
  return 'processing';
}

function publishTaskStatusText(status: PublishTask['status']) {
  const labels: Record<PublishTask['status'], string> = {
    pending: '等待中',
    running: '发布中',
    succeeded: '已完成',
    failed: '失败',
    canceled: '已取消',
  };
  return labels[status] || status;
}
