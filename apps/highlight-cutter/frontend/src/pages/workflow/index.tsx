import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  Upload,
} from 'antd';
import {
  DeleteOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { useEffect, useMemo, useRef, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { getHealth, getVideos, scanVideos } from '@/services/api';
import { uploadVideosWithProgress } from '@/services/upload';
import {
  createIntroTemplate,
  deleteIntroTemplate,
  generateIntroTemplateVisual,
  getIntroWorkflowTask,
  getIntroTemplates,
  runIntroWorkflow,
  updateIntroTemplate,
  uploadIntroTemplateAsset,
  type IntroTemplateAsset,
  type IntroWorkflowRunResult,
  type IntroWorkflowTask,
  type IntroTemplate,
} from '@/services/workflow';
import type { Health } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Paragraph, Text } = Typography;
const { TextArea } = Input;
const VIDEO_EXTENSIONS = ['.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi'];
const VIDEO_ACCEPT = 'video/*,.mp4,.mov,.m4v,.mkv,.webm,.avi';

type PresetFormValues = {
  dramaName: string;
  style: string;
  brief?: string;
};

const defaultPresetValues: PresetFormValues = {
  dramaName: '',
  style: '强冲突快节奏',
  brief: '',
};

const DEFAULT_INTRO_DURATION = 2;

function isVideoFile(file: File) {
  const fileName = file.name.toLowerCase();
  return VIDEO_EXTENSIONS.some((extension) => fileName.endsWith(extension));
}

function isActiveWorkflowStatus(status?: string) {
  return status === 'pending' || status === 'running';
}

function summarizeOrchestration(orchestration?: any) {
  if (!orchestration) return '等待多模型决策结果。';
  const gemini = orchestration.gemini || {};
  const parts = [
    gemini.visual_concept ? `Gemini：${gemini.visual_concept}` : gemini.error ? `Gemini：${gemini.error}` : '',
    orchestration.video?.mode ? '已生成视频预览。' : '',
  ].filter(Boolean);
  return parts.join('\n') || '多模型决策已完成。';
}

export default function WorkflowPage() {
  const { message } = App.useApp();
  const [health, setHealth] = useState<Health | null>(null);
  const [templates, setTemplates] = useState<IntroTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [savingPreset, setSavingPreset] = useState(false);
  const [generatingVisuals, setGeneratingVisuals] = useState(false);
  const [uploadingReferenceImage, setUploadingReferenceImage] = useState(false);
  const [referenceImage, setReferenceImage] = useState<IntroTemplateAsset | null>(null);
  const [importingVideos, setImportingVideos] = useState(false);
  const [importHint, setImportHint] = useState('支持多选视频或直接选择文件夹，自动过滤非视频文件。');
  const [importedVideoCount, setImportedVideoCount] = useState(0);
  const [workflowVideoIds, setWorkflowVideoIds] = useState<number[]>([]);
  const [runningWorkflow, setRunningWorkflow] = useState(false);
  const [workflowResult, setWorkflowResult] = useState<IntroWorkflowRunResult | null>(null);
  const [workflowTask, setWorkflowTask] = useState<IntroWorkflowTask | null>(null);
  const [generatedVisuals, setGeneratedVisuals] = useState<{
    intro?: { path: string; url: string; videoUrl?: string; orchestration?: any };
    outro?: { path: string; url: string; videoUrl?: string; orchestration?: any };
  }>({});
  const [form] = Form.useForm<PresetFormValues>();
  const uploadXhrRef = useRef<XMLHttpRequest | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
    loadTemplates();
  }, []);

  useEffect(() => {
    if (!workflowTask?.id || !isActiveWorkflowStatus(workflowTask.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const nextTask = await getIntroWorkflowTask(workflowTask.id);
        setWorkflowTask(nextTask);
        setWorkflowResult({ generated: nextTask.generated, failed: nextTask.failed });
        setRunningWorkflow(isActiveWorkflowStatus(nextTask.status));
        if (!isActiveWorkflowStatus(nextTask.status)) {
          if (nextTask.generated.length) message.success(`工作流完成：生成 ${nextTask.generated.length} 个产物`);
          if (nextTask.failed.length) message.warning(`有 ${nextTask.failed.length} 个视频处理失败`);
        }
      } catch (error) {
        setRunningWorkflow(false);
        message.error(getErrorMessage(error));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [message, workflowTask?.id, workflowTask?.status]);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedTemplateId) || templates[0],
    [selectedTemplateId, templates],
  );
  const templateOptions = useMemo(
    () =>
      templates.map((template) => ({
        value: template.id,
        label: `${template.name}${template.status === 'ready' ? '' : '（草案）'}`,
      })),
    [templates],
  );
  const canRunWorkflow = Boolean(selectedTemplate && workflowVideoIds.length && !runningWorkflow);

  async function loadTemplates() {
    setLoadingTemplates(true);
    try {
      const nextTemplates = await getIntroTemplates();
      setTemplates(nextTemplates);
      setSelectedTemplateId((current) => current || nextTemplates[0]?.id || null);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoadingTemplates(false);
    }
  }

  async function presetIntro(values: PresetFormValues) {
    setSavingPreset(true);
    try {
      const template = await createIntroTemplate({
        name: `${values.dramaName} 固定模板`,
        drama_name: values.dramaName,
        style: values.style,
        summary: `${values.style}：批量插入后续剧集开头和结尾。`,
        duration: DEFAULT_INTRO_DURATION,
        image_path: referenceImage?.path || '',
        image_url: referenceImage?.url || '',
        intro_image_path: generatedVisuals.intro?.path || '',
        intro_image_url: generatedVisuals.intro?.url || '',
        outro_image_path: generatedVisuals.outro?.path || '',
        outro_image_url: generatedVisuals.outro?.url || '',
        prompt: values.brief || '',
        source: 'ai',
        status: 'draft',
      });
      setTemplates((current) => [template, ...current]);
      setSelectedTemplateId(template.id);
      form.resetFields();
      form.setFieldsValue(defaultPresetValues);
      setReferenceImage(null);
      setGeneratedVisuals({});
      setTemplateModalOpen(false);
      message.success('固定模板已保存到数据库');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setSavingPreset(false);
    }
  }

  async function generateTemplateVisuals() {
    const values = form.getFieldsValue();
    if (!values.dramaName?.trim()) {
      message.warning('请先填写短剧名称');
      return;
    }
    setGeneratingVisuals(true);
    try {
      const [intro, outro] = await Promise.all([
        generateIntroTemplateVisual({
          kind: 'intro',
          drama_name: values.dramaName,
          style: values.style,
          brief: values.brief,
          duration: DEFAULT_INTRO_DURATION,
          reference_image_path: referenceImage?.path || '',
        }),
        generateIntroTemplateVisual({
          kind: 'outro',
          drama_name: values.dramaName,
          style: values.style,
          brief: values.brief,
          duration: DEFAULT_INTRO_DURATION,
          reference_image_path: referenceImage?.path || '',
        }),
      ]);
      setGeneratedVisuals({
        intro: {
          path: intro.path,
          url: intro.url,
          videoUrl: intro.video_url,
          orchestration: intro.orchestration,
        },
        outro: {
          path: outro.path,
          url: outro.url,
          videoUrl: outro.video_url,
          orchestration: outro.orchestration,
        },
      });
      message.success('片头和片尾已生成');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setGeneratingVisuals(false);
    }
  }

  function submitPreset() {
    if (!generatedVisuals.intro?.path || !generatedVisuals.outro?.path) {
      message.warning('请先生成片头和片尾');
      return;
    }
    form.submit();
  }

  async function uploadReferenceImage(file: File) {
    setUploadingReferenceImage(true);
    try {
      const asset = await uploadIntroTemplateAsset(file);
      setReferenceImage(asset);
      message.success('参考图已上传');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setUploadingReferenceImage(false);
    }
  }

  async function importWorkflowVideos(files: File[]) {
    const videoFiles = files.filter(isVideoFile);
    if (!videoFiles.length) {
      message.warning('没有找到支持的视频文件');
      return;
    }
    setImportingVideos(true);
    setImportHint(`准备导入 ${videoFiles.length} 个视频`);
    try {
      const result = await uploadVideosWithProgress(videoFiles, uploadXhrRef, {
        onUnknownProgress: () => setImportHint(`正在导入 ${videoFiles.length} 个视频...`),
        onProgress: (_percent, _weighted, hint) => setImportHint(hint),
      });
      const scan = await scanVideos();
      const uploadedPaths = new Set(result.saved);
      const videos = await getVideos();
      const matchedVideoIds = videos
        .filter((video) => video.path && uploadedPaths.has(video.path))
        .map((video) => video.id);
      setImportedVideoCount((current) => current + result.saved.length);
      setWorkflowVideoIds((current) => Array.from(new Set([...current, ...matchedVideoIds])));
      setWorkflowResult(null);
      setWorkflowTask(null);
      setImportHint(`导入完成：上传 ${result.saved.length} 个视频，匹配 ${matchedVideoIds.length} 个可运行素材`);
      if (scan.failed.length) message.warning(`有 ${scan.failed.length} 个文件扫描失败`);
      if (!matchedVideoIds.length) message.warning('视频已上传，但没有匹配到可运行的视频记录，请刷新后重试');
      message.success('工作流素材已导入');
    } catch (error) {
      const text = getErrorMessage(error);
      setImportHint(`导入失败：${text}`);
      message.error(text);
    } finally {
      setImportingVideos(false);
    }
  }

  async function runWorkflow() {
    if (!selectedTemplate) {
      message.warning('请先选择固定模板');
      return;
    }
    if (!workflowVideoIds.length) {
      message.warning('请先导入工作流视频');
      return;
    }
    setRunningWorkflow(true);
    setWorkflowResult(null);
    setWorkflowTask(null);
    try {
      const task = await runIntroWorkflow({
        template_id: selectedTemplate.id,
        source_video_ids: workflowVideoIds,
      });
      setWorkflowTask(task);
      setWorkflowResult({ generated: task.generated, failed: task.failed });
      setRunningWorkflow(isActiveWorkflowStatus(task.status));
      message.success('工作流已提交到后台');
    } catch (error) {
      message.error(getErrorMessage(error));
      setRunningWorkflow(false);
    }
  }

  function handleWorkflowVideoSelection(file: File, fileList: File[]) {
    if ((file as File & { uid?: string }).uid !== (fileList[0] as File & { uid?: string } | undefined)?.uid) return;
    importWorkflowVideos(fileList);
  }

  async function markReady(template: IntroTemplate) {
    try {
      const nextTemplate = await updateIntroTemplate(template.id, { status: 'ready' });
      setTemplates((items) => items.map((item) => (item.id === nextTemplate.id ? nextTemplate : item)));
      message.success('模板已标记为可复用');
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  function confirmDeleteTemplate(template: IntroTemplate) {
    Modal.confirm({
      title: '删除模板',
      content: `确定删除「${template.name}」吗？删除后不会影响已经生成的视频文件。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteIntroTemplate(template.id);
          const nextTemplates = templates.filter((item) => item.id !== template.id);
          setTemplates(nextTemplates);
          setSelectedTemplateId(nextTemplates[0]?.id || null);
          message.success('模板已删除');
        } catch (error) {
          message.error(getErrorMessage(error));
        }
      },
    });
  }

  return (
    <>
      <WorkspaceLayout
        health={health}
        title="批量工作流"
        subtitle="后续剧集保留正片，批量插入模板片头和片尾，提高处理速度和分发效率。"
        actions={
          <Space>
            <Button icon={<ThunderboltOutlined />} onClick={() => setTemplateModalOpen(true)}>
              生成模板
            </Button>
            <Button icon={<ReloadOutlined />} onClick={loadTemplates} loading={loadingTemplates}>
              刷新模板
            </Button>
          </Space>
        }
      >
      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <Card title="运行工作流">
            <Row gutter={[16, 16]} align="stretch">
              <Col xs={24} lg={10}>
                <Space direction="vertical" size={12} className="full-width">
                  <Text strong>1. 选择片头片尾模板</Text>
                  <Select
                    className="full-width"
                    loading={loadingTemplates}
                    value={selectedTemplate?.id}
                    placeholder="选择一个模板"
                    options={templateOptions}
                    onChange={setSelectedTemplateId}
                    notFoundContent={<Empty description="暂无模板" />}
                  />
                  {selectedTemplate ? (
                    <div className="workflow-selected-panel">
                      <Space direction="vertical" size={6}>
                        <Space wrap>
                          <Tag color={selectedTemplate.status === 'ready' ? 'success' : 'processing'}>
                            {selectedTemplate.status === 'ready' ? '可复用' : '草案'}
                          </Tag>
                          <Tag>{selectedTemplate.duration}s</Tag>
                          {selectedTemplate.intro_image_url && <Tag color="blue">片头图</Tag>}
                          {selectedTemplate.outro_image_url && <Tag color="geekblue">片尾图</Tag>}
                        </Space>
                        <Text strong>{selectedTemplate.name}</Text>
                        <Paragraph className="compact-paragraph">
                          {selectedTemplate.summary || selectedTemplate.prompt || '这个模板会插入到所选视频的开头和结尾。'}
                        </Paragraph>
                        <Space wrap>
                          {selectedTemplate.status !== 'ready' && (
                            <Button size="small" icon={<SaveOutlined />} onClick={() => markReady(selectedTemplate)}>
                              标记可复用
                            </Button>
                          )}
                          <Button
                            danger
                            size="small"
                            icon={<DeleteOutlined />}
                            onClick={() => confirmDeleteTemplate(selectedTemplate)}
                          >
                            删除模板
                          </Button>
                        </Space>
                      </Space>
                    </div>
                  ) : (
                    <Empty description="先生成或刷新模板" />
                  )}
                </Space>
              </Col>

              <Col xs={24} lg={14}>
                <Space direction="vertical" size={12} className="full-width">
                  <div className="workflow-run-header">
                    <Space direction="vertical" size={2}>
                      <Text strong>2. 导入视频并运行</Text>
                      <Text type="secondary">已导入 {importedVideoCount} 个，当前可运行 {workflowVideoIds.length} 个。</Text>
                    </Space>
                    <Button
                      type="primary"
                      size="large"
                      icon={<PlayCircleOutlined />}
                      loading={runningWorkflow}
                      disabled={!canRunWorkflow}
                      onClick={runWorkflow}
                    >
                      运行工作流
                    </Button>
                  </div>
                  <Space wrap>
                    <Upload
                      directory
                      multiple
                      accept={VIDEO_ACCEPT}
                      showUploadList={false}
                      disabled={importingVideos}
                      beforeUpload={(file, fileList) => {
                        handleWorkflowVideoSelection(file as unknown as File, fileList as unknown as File[]);
                        return false;
                      }}
                    >
                      <Button icon={<FolderOpenOutlined />} loading={importingVideos}>
                        选择文件夹
                      </Button>
                    </Upload>
                    <Upload
                      multiple
                      accept={VIDEO_ACCEPT}
                      showUploadList={false}
                      disabled={importingVideos}
                      beforeUpload={(file, fileList) => {
                        handleWorkflowVideoSelection(file as unknown as File, fileList as unknown as File[]);
                        return false;
                      }}
                    >
                      <Button icon={<UploadOutlined />} loading={importingVideos}>
                        选择多个视频
                      </Button>
                    </Upload>
                  </Space>
                  <Upload.Dragger
                    className="workflow-compact-dragger"
                    multiple
                    accept={VIDEO_ACCEPT}
                    showUploadList={false}
                    disabled={importingVideos}
                    beforeUpload={(file, fileList) => {
                      handleWorkflowVideoSelection(file as unknown as File, fileList as unknown as File[]);
                      return false;
                    }}
                  >
                    <p className="ant-upload-drag-icon">
                      <UploadOutlined />
                    </p>
                    <p className="ant-upload-text">拖入视频或文件夹</p>
                    <p className="ant-upload-hint">{importHint}</p>
                  </Upload.Dragger>
                </Space>
              </Col>
            </Row>
          </Card>
        </Col>

        <Col xs={24}>
          <Card title="任务进度和产物">
            <Space direction="vertical" size={16} className="full-width">
              {runningWorkflow && (
                <Alert
                  type="info"
                  showIcon
                  message="工作流已在后台运行"
                  description="可以继续留在页面查看进度和日志，视频较多或原片较长时需要等待一段时间。"
                />
              )}
              {workflowResult && (
                <Alert
                  type={workflowResult.failed.length ? 'warning' : 'success'}
                  showIcon
                  message={`已生成 ${workflowResult.generated.length} 个产物`}
                  description={workflowResult.failed.length ? `失败 ${workflowResult.failed.length} 个，请查看下方错误。` : '产物已写入项目产物库。'}
                />
              )}
              {workflowTask && (
                <Card size="small" title="后台任务进度">
                  <Space direction="vertical" size={12} className="full-width">
                    <Space wrap>
                      <Tag color={isActiveWorkflowStatus(workflowTask.status) ? 'processing' : workflowTask.status === 'failed' ? 'error' : 'success'}>
                        {workflowTask.status}
                      </Tag>
                      <Text type="secondary">任务 ID：{workflowTask.id}</Text>
                    </Space>
                    <Progress
                      percent={workflowTask.progress}
                      status={workflowTask.status === 'failed' ? 'exception' : isActiveWorkflowStatus(workflowTask.status) ? 'active' : 'success'}
                    />
                    <Text>{workflowTask.message}</Text>
                    <List
                      size="small"
                      dataSource={workflowTask.logs.slice(-8).reverse()}
                      locale={{ emptyText: <Empty description="暂无日志" /> }}
                      renderItem={(line) => (
                        <List.Item>
                          <Space direction="vertical" size={2}>
                            <Text type={line.level === 'error' ? 'danger' : 'secondary'}>{line.time}</Text>
                            <Text>{line.message}</Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </Space>
                </Card>
              )}
              {!workflowTask && !workflowResult && <Empty description="导入视频并运行后，这里会显示后台进度和生成产物" />}
              {workflowResult?.generated.length ? (
                <List
                  size="small"
                  dataSource={workflowResult.generated}
                  renderItem={(asset) => (
                    <List.Item
                      actions={[
                        <Button key="download" type="link" href={asset.download_url} target="_blank">
                          下载
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={asset.title}
                        description={asset.source_video_name || asset.output_path}
                      />
                    </List.Item>
                  )}
                />
              ) : null}
              {workflowResult?.failed.length ? (
                <List
                  size="small"
                  dataSource={workflowResult.failed}
                  renderItem={(item) => (
                    <List.Item>
                      <Text type="danger">视频 ID {item.video_id}：{item.error}</Text>
                    </List.Item>
                  )}
                />
              ) : null}
            </Space>
          </Card>
        </Col>
      </Row>
      </WorkspaceLayout>
      <Modal
        title="AI 生成固定模板"
        open={templateModalOpen}
        onCancel={() => setTemplateModalOpen(false)}
        footer={null}
        width={860}
        destroyOnClose={false}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={defaultPresetValues}
          onFinish={presetIntro}
        >
          <Row gutter={12}>
            <Col xs={24} md={10}>
              <Form.Item name="dramaName" label="短剧名称" rules={[{ required: true, message: '请输入短剧名称' }]}>
                <Input placeholder="例如：逆袭女王" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="style" label="片头风格">
                <Select
                  options={[
                    { value: '强冲突快节奏', label: '强冲突快节奏' },
                    { value: '情绪悬念', label: '情绪悬念' },
                    { value: '反转爽感', label: '反转爽感' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="brief" label="补充要求">
            <TextArea rows={4} placeholder="写明片头台词方向、是否复用首集前三集高光、目标平台风格等。" />
          </Form.Item>
          <Form.Item label="参考图">
            <Space direction="vertical" size={10} className="full-width">
              <Upload
                accept="image/*"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(file) => {
                  uploadReferenceImage(file);
                  return false;
                }}
              >
                <Button icon={<UploadOutlined />} loading={uploadingReferenceImage}>
                  上传参考图
                </Button>
              </Upload>
              {referenceImage ? (
                <div className="workflow-reference-image">
                  <img src={referenceImage.url} alt="固定模板参考图" />
                  <Space direction="vertical" size={4}>
                    <Text strong>{referenceImage.filename}</Text>
                    <Text type="secondary">创建模板时会把这张图保存为片头生成参考。</Text>
                    <Button size="small" icon={<DeleteOutlined />} onClick={() => setReferenceImage(null)}>
                      移除
                    </Button>
                  </Space>
                </div>
              ) : (
                <Text type="secondary">可上传海报、截图或风格参考图，辅助 AI 预制固定模板。</Text>
              )}
            </Space>
          </Form.Item>
          <Form.Item label="生成片头片尾">
            <Space direction="vertical" size={12} className="full-width">
              <Button
                icon={<ThunderboltOutlined />}
                loading={generatingVisuals}
                disabled={uploadingReferenceImage}
                onClick={generateTemplateVisuals}
              >
                生成
              </Button>
              {(generatedVisuals.intro || generatedVisuals.outro) && (
                <Row gutter={[12, 12]}>
                  {generatedVisuals.intro && (
                    <Col xs={24} md={12}>
                      <div className="workflow-generated-image">
                        <img src={generatedVisuals.intro.url} alt="GPT Image 2 片头图" />
                        <Text strong>片头图</Text>
                        {generatedVisuals.intro.videoUrl && (
                          <video className="asset-preview-video" src={generatedVisuals.intro.videoUrl} controls />
                        )}
                        <Paragraph className="compact-paragraph">
                          {summarizeOrchestration(generatedVisuals.intro.orchestration)}
                        </Paragraph>
                      </div>
                    </Col>
                  )}
                  {generatedVisuals.outro && (
                    <Col xs={24} md={12}>
                      <div className="workflow-generated-image">
                        <img src={generatedVisuals.outro.url} alt="GPT Image 2 片尾图" />
                        <Text strong>片尾图</Text>
                        {generatedVisuals.outro.videoUrl && (
                          <video className="asset-preview-video" src={generatedVisuals.outro.videoUrl} controls />
                        )}
                        <Paragraph className="compact-paragraph">
                          {summarizeOrchestration(generatedVisuals.outro.orchestration)}
                        </Paragraph>
                      </div>
                    </Col>
                  )}
                </Row>
              )}
              <Text type="secondary">Gemini 参与视觉策略，GPT Image 负责出图，后端会同步生成视频预览。</Text>
            </Space>
          </Form.Item>
          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={savingPreset}
              disabled={uploadingReferenceImage || generatingVisuals}
              onClick={submitPreset}
            >
              保存
            </Button>
            <Button onClick={() => setTemplateModalOpen(false)}>取消</Button>
          </Space>
        </Form>
      </Modal>
    </>
  );
}
