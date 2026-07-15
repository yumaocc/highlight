import { App, Button, Card, Col, Descriptions, Drawer, Empty, Form, Input, InputNumber, List, Modal, Popconfirm, Progress, Row, Select, Space, Table, Tag, Timeline, Typography } from 'antd';
import { CheckCircleOutlined, CloudDownloadOutlined, ClockCircleOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, EyeOutlined, FolderOpenOutlined, LoadingOutlined, PlayCircleOutlined, ReloadOutlined, SearchOutlined, SendOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { StatusTag } from '@/components/common/StatusTag';
import { WorkbenchHero } from '@/components/dashboard/WorkbenchHero';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import {
  clearUploadedVideos,
  createProject,
  createPipelineRuns,
  createResourceImport,
  deleteProject,
  getHealth,
  getPipelineRun,
  getPipelineRunArtifacts,
  getPipelineTemplates,
  getProjectAssets,
  getProjectPipelineRuns,
  getProjects,
  getResourceImport,
  getVideo,
  getVideos,
  scanVideos,
  searchQingqueResources,
} from '@/services/api';
import { uploadVideosWithProgress } from '@/services/upload';
import type {
  GeneratedAsset,
  Health,
  PipelineArtifact,
  PipelineRun,
  PipelineTemplate,
  Project,
  QingqueResourceMatch,
  ResourceImportTask,
  TaskStatus,
  TraceMessage,
  Video,
} from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';
import { formatDuration, formatSize } from '@/utils/format';

const { Text } = Typography;
const DEFAULT_TEMPLATE_KEY = 'story_quality_cut';
type ResourceImportFormValues = { baiduUrl: string; extractCode?: string; episodeLimit: number; dramaName?: string };

export default function Dashboard() {
  const { message, modal } = App.useApp();
  const [health, setHealth] = useState<Health | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectListOpen, setProjectListOpen] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<number | null>(null);
  const [projectForm] = Form.useForm<{ name: string; description?: string }>();
  const [resourceImportForm] = Form.useForm<ResourceImportFormValues>();
  const [videos, setVideos] = useState<Video[]>([]);
  const [assets, setAssets] = useState<GeneratedAsset[]>([]);
  const [pipelineTemplates, setPipelineTemplates] = useState<PipelineTemplate[]>([]);
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRun[]>([]);
  const [pipelineArtifacts, setPipelineArtifacts] = useState<PipelineArtifact[]>([]);
  const [selectedPipelineRun, setSelectedPipelineRun] = useState<PipelineRun | null>(null);
  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const [assetPreview, setAssetPreview] = useState<{ title: string; url: string } | null>(null);
  const [status, setStatus] = useState<TaskStatus>({ text: '待命', type: 'default' });
  const [traceMessages, setTraceMessages] = useState<TraceMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploadHint, setUploadHint] = useState('支持选择文件或文件夹；自动过滤 mp4、mov、mkv、webm、avi');
  const [generationTemplateKey, setGenerationTemplateKey] = useState(DEFAULT_TEMPLATE_KEY);
  const [resourceImportTask, setResourceImportTask] = useState<ResourceImportTask | null>(null);
  const [resourceImporting, setResourceImporting] = useState(false);
  const [qingqueSearching, setQingqueSearching] = useState(false);
  const [qingqueMatches, setQingqueMatches] = useState<QingqueResourceMatch[]>([]);
  const uploadXhrRef = useRef<XMLHttpRequest | null>(null);

  useEffect(() => {
    loadHealth();
    loadPipelineTemplates();
    loadProjects();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setVideos([]);
    setAssets([]);
    setPipelineRuns([]);
    setSelectedVideoId(null);
    setSelectedVideo(null);
    setSelectedPipelineRun(null);
    setPipelineArtifacts([]);
    loadVideos(selectedProjectId);
    loadAssets(selectedProjectId);
    loadPipelineRuns(selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!resourceImportTask?.id) return;
    if (!isActiveStatus(resourceImportTask.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const nextTask = await getResourceImport(resourceImportTask.id);
        setResourceImportTask(nextTask);
        setStatus({ text: nextTask.message || '正在导入百度云资源', type: nextTask.status === 'failed' ? 'error' : 'default' });
        if (!isActiveStatus(nextTask.status)) {
          setResourceImporting(false);
          if (nextTask.status === 'succeeded') {
            finishTask(`完成：导入 ${nextTask.downloaded.length} 个视频，创建 ${nextTask.pipeline_runs.length} 个剪辑任务`);
            message.success('百度云资源已导入，剪辑任务已创建');
            await Promise.all([
              loadVideos(nextTask.project_id),
              loadAssets(nextTask.project_id),
              loadPipelineRuns(nextTask.project_id),
              loadProjects(),
            ]);
          } else if (nextTask.status === 'failed') {
            finishTask(`失败：${nextTask.message || '百度云资源导入失败'}`);
            message.error(nextTask.message || '百度云资源导入失败');
          }
        }
      } catch (error) {
        setResourceImporting(false);
        finishTask(`失败：${getErrorMessage(error)}`);
        message.error(getErrorMessage(error));
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [resourceImportTask?.id, resourceImportTask?.status]);

  const currentProject = projects.find((project) => project.id === selectedProjectId) || null;
  const selectedTitle = selectedVideo
    ? selectedVideo.name
    : currentProject
      ? currentProject.name
      : '短剧项目';
  const selectedMeta = selectedVideo
    ? `${formatDuration(selectedVideo.duration)} · ${formatSize(selectedVideo.size_bytes)} · ${selectedVideo.width || 0}x${selectedVideo.height || 0} · ${selectedVideo.codec || 'unknown'}`
    : currentProject
      ? `${currentProject.video_count || videos.length} 个素材 · ${currentProject.asset_count || assets.length} 个产物`
      : '上传素材后，在生成流程中选择管道模板。';
  const selectedTemplate = pipelineTemplates.find((item) => item.key === generationTemplateKey) || pipelineTemplates.find((item) => item.key === DEFAULT_TEMPLATE_KEY) || pipelineTemplates[0];
  const generationParams = useMemo(() => defaultParamsForTemplate(selectedTemplate), [selectedTemplate]);
  const generationVideoIds = useMemo(() => videos.map((video) => video.id), [videos]);
  const activeRuns = pipelineRuns.filter((run) => run.status === 'pending' || run.status === 'running');
  const latestRun = pipelineRuns[0];
  const latestTaskMessage = traceMessages[traceMessages.length - 1];
  async function loadHealth() {
    try {
      setHealth(await getHealth());
    } catch (error) {
      setStatus({ text: getErrorMessage(error), type: 'error' });
    }
  }

  async function loadVideos(projectId = selectedProjectId) {
    if (!projectId) return;
    try {
      setVideos(await getVideos(projectId));
    } catch (error) {
      setStatus({ text: getErrorMessage(error), type: 'error' });
    }
  }

  async function loadProjects() {
    try {
      const nextProjects = await getProjects();
      setProjects(nextProjects);
      if (!selectedProjectId && nextProjects.length) setSelectedProjectId(nextProjects[0].id);
      if (selectedProjectId && nextProjects.length && !nextProjects.some((project) => project.id === selectedProjectId)) {
        setSelectedProjectId(nextProjects[0].id);
      }
    } catch (error) {
      setStatus({ text: getErrorMessage(error), type: 'error' });
    }
  }

  async function loadPipelineTemplates() {
    try {
      const templates = await getPipelineTemplates();
      setPipelineTemplates(templates);
      if (!templates.some((item) => item.key === generationTemplateKey)) {
        setGenerationTemplateKey(templates.find((item) => item.key === DEFAULT_TEMPLATE_KEY)?.key || templates[0]?.key || DEFAULT_TEMPLATE_KEY);
      }
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  async function loadPipelineRuns(projectId = selectedProjectId) {
    if (!projectId) return;
    try {
      setPipelineRuns(await getProjectPipelineRuns(projectId));
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  async function loadAssets(projectId = selectedProjectId) {
    if (!projectId) return;
    try {
      setAssets(await getProjectAssets(projectId));
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  async function submitProject(values: { name: string; description?: string }) {
    setCreatingProject(true);
    try {
      const project = await createProject({ name: values.name, description: values.description || '', status: 'active' });
      setProjects((items) => [project, ...items]);
      setSelectedProjectId(project.id);
      setProjectModalOpen(false);
      projectForm.resetFields();
      message.success('短剧项目已创建');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setCreatingProject(false);
    }
  }

  async function removeProject(project: Project) {
    setDeletingProjectId(project.id);
    try {
      const result = await deleteProject(project.id);
      const nextProjects = projects.filter((item) => item.id !== project.id);
      setProjects(nextProjects);
      if (selectedProjectId === project.id) {
        const nextProjectId = nextProjects[0]?.id || null;
        setSelectedProjectId(nextProjectId);
        if (!nextProjectId) {
          setVideos([]);
          setAssets([]);
          setPipelineRuns([]);
          setSelectedVideoId(null);
          setSelectedVideo(null);
        }
      }
      const failed = result.failed?.length ? `，${result.failed.length} 个清理失败` : '';
      message.success(`项目已删除：${result.removed_videos} 个素材，${result.removed_assets} 个产物记录${failed}`);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setDeletingProjectId(null);
    }
  }

  async function selectVideo(videoId: number) {
    try {
      const video = await getVideo(videoId, selectedProjectId);
      setSelectedVideoId(videoId);
      setSelectedVideo(video);
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  async function openPipelineRun(run: PipelineRun) {
    try {
      const [detail, artifacts] = await Promise.all([
        getPipelineRun(run.id, selectedProjectId),
        getPipelineRunArtifacts(run.id, selectedProjectId),
      ]);
      setSelectedPipelineRun(detail);
      setPipelineArtifacts(artifacts);
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  }

  function startTask(label: string) {
    setBusy(true);
    setTraceMessages([{ role: 'system', title: '任务开始', body: label, percent: 5 }]);
  }

  function finishTask(text: string) {
    setTraceMessages((current) => [...current, { role: 'system', title: '任务结束', body: text, percent: 100 }]);
    setBusy(false);
  }

  async function handleUploadFiles(files: File[]) {
    if (!files.length) return;
    startTask(`准备上传 ${files.length} 个视频`);
    setUploadHint(`准备上传 ${files.length} 个视频`);
    setStatus({ text: `准备上传 ${files.length} 个视频...`, type: 'default' });
    try {
      if (!selectedProjectId) {
        message.error('请先创建或选择短剧项目');
        finishTask('失败：未选择短剧项目');
        return;
      }
      const result = await uploadVideosWithProgress(files, uploadXhrRef, {
        onUnknownProgress: () => {
          setStatus({ text: `正在上传 ${files.length} 个视频...`, type: 'default' });
        },
        onProgress: (percent, weighted, hint) => {
          setStatus({ text: `正在上传 ${files.length} 个视频：${percent}%`, type: 'default' });
          setUploadHint(hint);
        },
      }, selectedProjectId);
      setStatus({ text: `上传完成：${result.saved.length} 个视频，正在扫描...`, type: 'default' });
      const scan = await scanVideos(selectedProjectId);
      await loadVideos(selectedProjectId);
      await loadProjects();
      setStatus({ text: `扫描完成：${scan.indexed} 个视频`, type: scan.failed.length ? 'warning' : 'success' });
      finishTask(`完成：上传 ${result.saved.length} 个视频，扫描 ${scan.indexed} 个视频`);
      setUploadHint('上传完成，可继续添加视频');
    } catch (error) {
      const text = getErrorMessage(error);
      setStatus({ text, type: 'error' });
      finishTask(`失败：${text}`);
      setUploadHint('上传失败，请重试');
    }
  }

  async function submitResourceImport(values: ResourceImportFormValues) {
    if (!selectedProjectId) {
      message.error('请先创建或选择短剧项目');
      return;
    }
    setResourceImporting(true);
    startTask('正在提交百度云资源导入任务');
    setStatus({ text: '正在提交百度云资源导入任务...', type: 'default' });
    try {
      const task = await createResourceImport({
        project_id: selectedProjectId,
        baidu_url: values.baiduUrl,
        extract_code: values.extractCode?.trim() || '',
        drama_name: values.dramaName?.trim() || '',
        episode_limit: values.episodeLimit || 5,
        pipeline_template_key: generationTemplateKey || DEFAULT_TEMPLATE_KEY,
        enqueue_pipeline: true,
      });
      setResourceImportTask(task);
      setTraceMessages((current) => [
        ...current,
        { role: 'system', title: '百度云导入', body: task.message, percent: task.progress },
      ]);
      message.success('资源导入任务已提交');
    } catch (error) {
      const text = getErrorMessage(error);
      setResourceImporting(false);
      setStatus({ text, type: 'error' });
      finishTask(`失败：${text}`);
      message.error(text);
    }
  }

  async function lookupQingqueResource() {
    const dramaName = resourceImportForm.getFieldValue('dramaName')?.trim();
    if (!dramaName) {
      message.error('请输入短剧名称');
      return;
    }
    setQingqueSearching(true);
    try {
      const matches = await searchQingqueResources(dramaName, 8);
      setQingqueMatches(matches);
      if (matches.length) {
        message.success(`找到 ${matches.length} 条资源候选`);
      } else {
        message.warning('青雀文档中没有找到匹配资源');
      }
    } catch (error) {
      const text = getErrorMessage(error);
      message.error(text);
    } finally {
      setQingqueSearching(false);
    }
  }

  async function copyResourceText(text: string, label: string) {
    if (!text) {
      message.warning(`${label}为空`);
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      message.success(`${label}已复制`);
    } catch {
      message.error(`${label}复制失败`);
    }
  }

  function confirmClearVideos() {
    modal.confirm({
      title: '确认清空已上传视频？',
      content: '这会真实删除 inputs/ 中的源视频，并清理 work/ 临时音频和关键帧缓存；已导出的高光视频会保留。',
      okText: '清空',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: clearVideos,
    });
  }

  async function clearVideos() {
    setBusy(true);
    setStatus({ text: '正在清空已上传视频...', type: 'default' });
    try {
      const result = await clearUploadedVideos(selectedProjectId);
      setSelectedVideoId(null);
      setSelectedVideo(null);
      setTraceMessages([]);
      await loadVideos(selectedProjectId);
      await loadAssets(selectedProjectId);
      await loadProjects();
      setStatus({ text: `已清空：删除 ${result.removed_files} 个源视频，${result.removed_work_files} 个临时文件`, type: 'success' });
    } catch (error) {
      setStatus({ text: getErrorMessage(error), type: 'error' });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!selectedProjectId) return;
    const hasActiveRun = pipelineRuns.some((run) => run.status === 'pending' || run.status === 'running');
    if (!hasActiveRun) return;
      const timer = window.setInterval(() => {
        loadPipelineRuns(selectedProjectId);
        loadAssets(selectedProjectId);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [pipelineRuns, selectedProjectId]);

  async function generateVideo() {
    if (!selectedTemplate) {
      message.error('还没有可用的生成模板');
      return;
    }
    await runPipelineWithSourceIds(
      selectedTemplate.key,
      generationParams,
      generationVideoIds,
      `正在生成：${selectedTemplate.name}`,
      selectedTemplate.run_strategy === 'aggregate',
    );
  }

  async function runPipelineWithSourceIds(
    templateKey: string,
    params: Record<string, any>,
    sourceVideoIds: number[],
    label: string,
    enqueue = false,
  ) {
    if (!selectedProjectId) {
      message.error('请先选择短剧项目');
      return;
    }
    if (!sourceVideoIds.length) {
      message.error('请选择要进入管道的素材');
      return;
    }
    startTask(label);
    setStatus({ text: '管道生成中...', type: 'default' });
    try {
      const result = await createPipelineRuns(
        selectedProjectId,
        {
          template_key: templateKey,
          source_video_ids: sourceVideoIds,
          params,
        },
        enqueue,
      );
      const succeeded = result.runs.filter((run) => run.status === 'succeeded').length;
      const failed = result.runs.filter((run) => run.status === 'failed').length;
      const pending = result.runs.filter((run) => run.status === 'pending').length;
      setPipelineRuns((items) => [...result.runs, ...items]);
      await loadAssets(selectedProjectId);
      await loadProjects();
      setStatus({
        text: enqueue ? `已加入队列：${pending} 个任务` : `管道完成：成功 ${succeeded} 个，失败 ${failed} 个`,
        type: failed ? 'warning' : 'success',
      });
      finishTask(enqueue ? `完成：${result.runs.length} 个管道运行已加入队列` : `完成：创建 ${result.runs.length} 个管道运行`);
    } catch (error) {
      const text = getErrorMessage(error);
      setStatus({ text, type: 'error' });
      finishTask(`失败：${text}`);
    }
  }

  return (
    <WorkspaceLayout
      health={health}
      title={selectedTitle}
      subtitle={<Text type="secondary">{selectedMeta}</Text>}
      actions={<StatusTag status={status} />}
    >
          <Space direction="vertical" size={18} className="full-width home-console home-redesign">
            <Card className="home-topbar-card">
              <div className="home-topbar">
                <Space className="home-project-control" wrap>
                  <Button icon={<FolderOpenOutlined />} onClick={() => setProjectListOpen(true)}>
                    项目
                  </Button>
                  <Select
                    className="home-project-select"
                    value={selectedProjectId || undefined}
                    placeholder="选择短剧项目"
                    options={projects.map((project) => ({
                      value: project.id,
                      label: `${project.name} · ${project.video_count || 0} 素材 · ${project.asset_count || 0} 产物`,
                    }))}
                    onChange={setSelectedProjectId}
                  />
                </Space>
                <Space className="home-topbar-actions" wrap>
                  <Button onClick={() => setProjectModalOpen(true)}>新建项目</Button>
                  <StatusTag status={status} />
                </Space>
              </div>
            </Card>

            <Row gutter={[18, 18]} align="stretch">
              <Col xs={24} xl={15}>
                <Space direction="vertical" size={16} className="full-width">
                  <DashboardPanel
                    title="上传视频素材"
                    description="拖入视频文件，或选择文件夹批量导入。"
                    extra={<Tag color={videos.length ? 'success' : 'default'}>{videos.length} 个素材</Tag>}
                  >
                    <WorkbenchHero busy={busy} uploadHint={uploadHint} onUploadFiles={handleUploadFiles} />
                    <ResourceImportPanel
                      form={resourceImportForm}
                      task={resourceImportTask}
                      loading={resourceImporting}
                      lookupLoading={qingqueSearching}
                      disabled={busy && !resourceImporting}
                      matches={qingqueMatches}
                      onLookup={lookupQingqueResource}
                      onCopy={copyResourceText}
                      onSubmit={submitResourceImport}
                    />
                  </DashboardPanel>

                  <Card className="home-generate-card">
                    <div className="home-generate-grid">
                      <Space direction="vertical" size={6} className="home-generate-copy">
                        <Text strong>生成视频</Text>
                        <Text type="secondary">{selectedTemplate?.description || '选择模式后生成短视频。'}</Text>
                      </Space>
                      <div className="home-generate-controls">
                        <Select
                          className="home-template-select"
                          value={selectedTemplate?.key}
                          placeholder="选择生成模式"
                          options={pipelineTemplates.map((template) => ({
                            value: template.key,
                            label: `${template.name} · ${templateModeLabel(template)}`,
                          }))}
                          onChange={setGenerationTemplateKey}
                        />
                        <Space className="home-generate-actions" wrap>
                          <Tag>{generationVideoIds.length} 个素材</Tag>
                          <Button onClick={() => loadPipelineRuns()} icon={<ReloadOutlined />}>
                            刷新
                          </Button>
                          <Button
                            type="primary"
                            icon={<PlayCircleOutlined />}
                            loading={busy}
                            disabled={!videos.length || !selectedTemplate}
                            onClick={generateVideo}
                          >
                            生成视频
                          </Button>
                        </Space>
                      </div>
                    </div>
                  </Card>

                  <DashboardPanel
                    title="素材列表"
                    description="当前项目中可参与生成的视频素材。"
                    extra={
                      <Space wrap>
                        <Tag>{videos.length} 个素材</Tag>
                        <Button danger size="small" icon={<DeleteOutlined />} onClick={confirmClearVideos} disabled={busy || !videos.length}>
                          清空
                        </Button>
                      </Space>
                    }
                  >
                    <SourceVideoTable
                      videos={videos}
                      selectedVideoId={selectedVideoId}
                      onSelectVideo={selectVideo}
                    />
                  </DashboardPanel>
                </Space>
              </Col>

              <Col xs={24} xl={9}>
                <Space direction="vertical" size={16} className="full-width">
                  <DashboardPanel
                    title="最近状态"
                    description={latestTaskMessage ? latestTaskMessage.body : '生成、上传和扫描状态会显示在这里。'}
                    extra={activeRuns.length > 0 ? <Tag color="processing">{activeRuns.length} 个运行中</Tag> : <Tag color={latestRun?.status === 'succeeded' ? 'success' : 'default'}>{latestRun ? statusLabel(latestRun.status) : '待命'}</Tag>}
                  >
                    <RecentStatusList
                      runs={pipelineRuns}
                      templates={pipelineTemplates}
                      latestTaskMessage={latestTaskMessage}
                      onOpenRun={openPipelineRun}
                    />
                  </DashboardPanel>

                  <DashboardPanel
                    title="生成产物"
                    description="预览、下载或发布生成后的视频。"
                    extra={<Tag color={assets.length ? 'success' : 'default'}>{assets.length} 个产物</Tag>}
                  >
                    <AssetList assets={assets} onPreview={setAssetPreview} />
                    <Button href="/publish" block>
                      打开发发布中心
                    </Button>
                  </DashboardPanel>
                </Space>
              </Col>
            </Row>
          </Space>
          <Modal
            title={assetPreview?.title || '视频预览'}
            open={Boolean(assetPreview)}
            footer={null}
            width={860}
            destroyOnClose
            onCancel={() => setAssetPreview(null)}
          >
            {assetPreview && <video className="asset-preview-video" src={assetPreview.url} controls autoPlay playsInline />}
          </Modal>
          <Modal
            title="新建短剧项目"
            open={projectModalOpen}
            onCancel={() => setProjectModalOpen(false)}
            footer={null}
            destroyOnClose
          >
            <Form form={projectForm} layout="vertical" onFinish={submitProject}>
              <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
                <Input placeholder="例如：霸总短剧第一季" />
              </Form.Item>
              <Form.Item name="description" label="项目说明">
                <Input.TextArea rows={3} placeholder="可填写剧情简介、投放方向或账号策略" />
              </Form.Item>
              <Space className="form-actions">
                <Button onClick={() => setProjectModalOpen(false)}>取消</Button>
                <Button type="primary" htmlType="submit" loading={creatingProject}>
                  创建
                </Button>
              </Space>
            </Form>
          </Modal>
          <Drawer
            title="短剧项目列表"
            open={projectListOpen}
            onClose={() => setProjectListOpen(false)}
            width={880}
            extra={
              <Button onClick={loadProjects}>
                刷新
              </Button>
            }
          >
            <Table
              rowKey="id"
              dataSource={projects}
              pagination={{ pageSize: 8, showSizeChanger: false }}
              columns={[
                {
                  title: '项目',
                  dataIndex: 'name',
                  render: (_, project) => (
                    <Space direction="vertical" size={4}>
                      <Space wrap>
                        <Text strong>{project.name}</Text>
                        {project.id === selectedProjectId && <Tag color="blue">当前</Tag>}
                        <Tag>{project.status}</Tag>
                      </Space>
                      <Text type="secondary">{project.description || '未填写说明'}</Text>
                    </Space>
                  ),
                },
                {
                  title: '内容',
                  width: 150,
                  render: (_, project) => (
                    <Space direction="vertical" size={2}>
                      <Text>{project.video_count || 0} 个素材</Text>
                      <Text>{project.asset_count || 0} 个产物</Text>
                    </Space>
                  ),
                },
                {
                  title: '更新时间',
                  dataIndex: 'updated_at',
                  width: 190,
                  responsive: ['md'],
                  render: (value) => <Text type="secondary">{value || '-'}</Text>,
                },
                {
                  title: '操作',
                  width: 180,
                  render: (_, project) => (
                    <Space>
                      <Button
                        size="small"
                        onClick={() => {
                          setSelectedProjectId(project.id);
                          setProjectListOpen(false);
                        }}
                      >
                        查看
                      </Button>
                      <Popconfirm
                        title="删除这个项目？"
                        description="会删除项目记录、素材索引和生成记录；已导出的成片文件会保留。"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true, loading: deletingProjectId === project.id }}
                        onConfirm={() => removeProject(project)}
                      >
                        <Button size="small" danger icon={<DeleteOutlined />} loading={deletingProjectId === project.id}>
                          删除
                        </Button>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          </Drawer>
          <PipelineRunDetailDrawer
            run={selectedPipelineRun}
            artifacts={pipelineArtifacts}
            templates={pipelineTemplates}
            onClose={() => {
              setSelectedPipelineRun(null);
              setPipelineArtifacts([]);
            }}
          />
    </WorkspaceLayout>
  );
}

function DashboardPanel({
  title,
  description,
  extra,
  children,
}: {
  title: string;
  description?: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className="dashboard-panel">
      <Space direction="vertical" size={14} className="full-width">
        <div className="dashboard-panel-head">
          <Space direction="vertical" size={2}>
            <Text strong>{title}</Text>
            {description && <Text type="secondary">{description}</Text>}
          </Space>
          {extra}
        </div>
        {children}
      </Space>
    </Card>
  );
}

function SourceVideoTable({
  videos,
  selectedVideoId,
  onSelectVideo,
}: {
  videos: Video[];
  selectedVideoId: number | null;
  onSelectVideo: (videoId: number) => void;
}) {
  return (
    <Table
      className="home-source-table"
      size="small"
      rowKey="id"
      dataSource={videos}
      pagination={videos.length > 6 ? { pageSize: 6, showSizeChanger: false } : false}
      rowClassName={(record) => (record.id === selectedVideoId ? 'selected-row' : '')}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有素材" /> }}
      columns={[
        {
          title: '素材',
          dataIndex: 'name',
          ellipsis: true,
          render: (value: string, record) => (
            <Button type="link" className="row-link" onClick={() => onSelectVideo(record.id)}>
              {value}
            </Button>
          ),
        },
        { title: '时长', dataIndex: 'duration', width: 96, render: formatDuration },
        { title: '大小', dataIndex: 'size_bytes', width: 104, render: formatSize },
        { title: '分辨率', width: 112, responsive: ['md'], render: (_, record) => `${record.width || 0}x${record.height || 0}` },
      ]}
    />
  );
}

function ResourceImportPanel({
  form,
  task,
  loading,
  lookupLoading,
  disabled,
  matches,
  onLookup,
  onCopy,
  onSubmit,
}: {
  form: ReturnType<typeof Form.useForm<ResourceImportFormValues>>[0];
  task: ResourceImportTask | null;
  loading: boolean;
  lookupLoading: boolean;
  disabled: boolean;
  matches: QingqueResourceMatch[];
  onLookup: () => void;
  onCopy: (text: string, label: string) => void;
  onSubmit: (values: ResourceImportFormValues) => void;
}) {
  const latestLog = task?.logs?.[task.logs.length - 1];
  return (
    <div className="resource-import-panel">
      <div className="resource-import-head">
        <Space direction="vertical" size={2}>
          <Text strong>从百度云导入</Text>
          <Text type="secondary">填写百度分享链接和提取码，自动转存、下载前几集并创建剪辑任务。</Text>
        </Space>
        {task && <Tag color={statusColor(task.status)}>{statusLabel(task.status)}</Tag>}
      </div>
      <Form
        form={form}
        layout="vertical"
        className="resource-import-form"
        initialValues={{ episodeLimit: 5 }}
        onFinish={onSubmit}
      >
        <div className="resource-lookup-row">
          <Form.Item name="dramaName" label="青雀资源查询" className="resource-import-path">
            <Input placeholder="输入短剧名称" allowClear disabled={lookupLoading} onPressEnter={onLookup} />
          </Form.Item>
          <Form.Item label=" " className="resource-import-submit">
            <Button icon={<SearchOutlined />} loading={lookupLoading} onClick={onLookup}>
              查找资源
            </Button>
          </Form.Item>
        </div>
        {matches.length > 0 && (
          <div className="resource-match-list">
            {matches.map((match) => (
              <div className="resource-match-item" key={`${match.sheet_id}-${match.row}-${match.baidu_url}`}>
                <Space direction="vertical" size={4} className="full-width">
                  <Space wrap size={6}>
                    <Text strong>{match.drama_name}</Text>
                    <Tag>{Math.round(match.score * 100)}%</Tag>
                    <Tag>{match.sheet_name} · 第 {match.row} 行</Tag>
                  </Space>
                  <Text className="resource-match-link" copyable={false}>{match.baidu_url}</Text>
                  <Space wrap size={8}>
                    {match.extract_code && <Tag color="blue">提取码 {match.extract_code}</Tag>}
                    <Button size="small" icon={<CopyOutlined />} onClick={() => onCopy(match.baidu_url, '百度云链接')}>
                      复制链接
                    </Button>
                    <Button size="small" icon={<CopyOutlined />} onClick={() => onCopy(match.extract_code, '提取码')}>
                      复制提取码
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      onClick={() => form.setFieldsValue({ baiduUrl: match.baidu_url, extractCode: match.extract_code, dramaName: match.drama_name })}
                    >
                      填入链接
                    </Button>
                  </Space>
                </Space>
              </div>
            ))}
          </div>
        )}
        <div className="resource-download-row">
          <Form.Item name="baiduUrl" label="百度分享链接" rules={[{ required: true, message: '请输入百度分享链接' }]} className="resource-import-path">
            <Input placeholder="https://pan.baidu.com/s/..." allowClear disabled={disabled || loading} />
          </Form.Item>
          <Form.Item name="extractCode" label="提取码" className="resource-import-count">
            <Input placeholder="可选" allowClear disabled={disabled || loading} />
          </Form.Item>
          <Form.Item name="episodeLimit" label="集数" className="resource-import-count">
            <InputNumber min={1} max={50} disabled={disabled || loading} />
          </Form.Item>
          <Form.Item label=" " className="resource-import-submit">
            <Button type="primary" htmlType="submit" icon={<CloudDownloadOutlined />} loading={loading} disabled={disabled}>
              导入并剪辑
            </Button>
          </Form.Item>
        </div>
      </Form>
      {task && (
        <Space direction="vertical" size={6} className="full-width resource-import-status">
          <Progress percent={task.progress || 0} status={task.status === 'failed' ? 'exception' : isActiveStatus(task.status) ? 'active' : 'success'} />
          <Text type={task.status === 'failed' ? 'danger' : 'secondary'}>{task.message}</Text>
          <Space wrap size={6}>
            <Tag>{task.downloaded.length} 个已下载</Tag>
            <Tag>{task.video_ids.length} 个入库素材</Tag>
            <Tag>{task.pipeline_runs.length} 个剪辑任务</Tag>
          </Space>
          {latestLog && <Text type="secondary">{latestLog.time} · {latestLog.message}</Text>}
        </Space>
      )}
    </div>
  );
}

function RecentStatusList({
  runs,
  templates,
  latestTaskMessage,
  onOpenRun,
}: {
  runs: PipelineRun[];
  templates: PipelineTemplate[];
  latestTaskMessage?: TraceMessage;
  onOpenRun: (run: PipelineRun) => void;
}) {
  const items = runs.slice(0, 4);
  if (!items.length && !latestTaskMessage) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无状态记录" />;
  }
  return (
    <List
      className="home-status-list"
      dataSource={items}
      header={latestTaskMessage ? (
        <div className="home-status-item home-status-current">
          <span className="home-status-icon"><LoadingOutlined /></span>
          <Space direction="vertical" size={2}>
            <Text strong>{latestTaskMessage.title}</Text>
            <Text type="secondary">{latestTaskMessage.body}</Text>
          </Space>
        </div>
      ) : null}
      renderItem={(run) => (
        <List.Item
          className="home-status-item"
          actions={[<Button key="detail" type="link" size="small" onClick={() => onOpenRun(run)}>详情</Button>]}
        >
          <span className="home-status-icon">{run.status === 'succeeded' ? <CheckCircleOutlined /> : run.status === 'running' ? <LoadingOutlined /> : <ClockCircleOutlined />}</span>
          <List.Item.Meta
            title={<Space wrap><Text strong>{templateName(templates, run.template_key)}</Text><Tag color={statusColor(run.status)}>{statusLabel(run.status)}</Tag></Space>}
            description={run.current_step || `${run.progress || 0}%`}
          />
        </List.Item>
      )}
    />
  );
}

function AssetList({
  assets,
  onPreview,
}: {
  assets: GeneratedAsset[];
  onPreview: (asset: { title: string; url: string }) => void;
}) {
  if (!assets.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有生成产物" />;
  return (
    <List
      className="home-asset-list"
      dataSource={assets.slice(0, 5)}
      renderItem={(asset) => (
        <List.Item
          actions={[
            <Button key="preview" type="text" icon={<EyeOutlined />} onClick={() => onPreview({ title: asset.title, url: asset.download_url })} />,
            <Button key="download" type="text" icon={<DownloadOutlined />} href={asset.download_url} />,
            <Button key="publish" type="text" icon={<SendOutlined />} href={`/publish?projectId=${asset.project_id}&assetIds=${asset.id}`} />,
          ]}
        >
          <List.Item.Meta
            title={<Space wrap><Text strong>{asset.title}</Text><Tag color={asset.type === 'promo' ? 'blue' : 'green'}>{assetTypeLabel(asset.type)}</Tag></Space>}
            description={asset.description || asset.source_video_name || asset.output_path}
          />
        </List.Item>
      )}
    />
  );
}

function PipelineRunDetailDrawer({
  run,
  artifacts,
  templates,
  onClose,
}: {
  run: PipelineRun | null;
  artifacts: PipelineArtifact[];
  templates: PipelineTemplate[];
  onClose: () => void;
}) {
  const steps = run?.steps || [];
  return (
    <Drawer title="生成详情" open={Boolean(run)} onClose={onClose} width={760} destroyOnClose>
      {run ? (
        <Space direction="vertical" size={16} className="full-width">
          <Descriptions size="small" bordered column={1}>
            <Descriptions.Item label="模板">{templateName(templates, run.template_key)}</Descriptions.Item>
            <Descriptions.Item label="素材">
              {(run.source_count || 0) > 1 ? `${run.source_count} 个素材` : run.source_video_name || run.source_video_id || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={statusColor(run.status)}>{statusLabel(run.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="进度">{run.progress || 0}%</Descriptions.Item>
            <Descriptions.Item label="当前步骤">{run.current_step || '-'}</Descriptions.Item>
            <Descriptions.Item label="错误">{run.error || '-'}</Descriptions.Item>
          </Descriptions>

          <div>
            <Text strong>步骤</Text>
            {steps.length ? (
              <Timeline
                className="pipeline-timeline"
                items={steps.map((step) => ({
                  color: step.status === 'succeeded' ? 'green' : step.status === 'failed' ? 'red' : step.status === 'running' ? 'blue' : 'gray',
                  children: (
                    <Space direction="vertical" size={2}>
                      <Space wrap>
                        <Text strong>{step.name}</Text>
                        <Tag>{step.step_key}</Tag>
                        <Tag color={statusColor(step.status)}>{statusLabel(step.status)}</Tag>
                        <Text type="secondary">{step.progress || 0}%</Text>
                      </Space>
                      {step.error && <Text type="danger">{step.error}</Text>}
                    </Space>
                  ),
                }))}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无步骤记录" />
            )}
          </div>

          <div>
            <Text strong>产物记录</Text>
            {artifacts.length ? (
              <Table
                size="small"
                rowKey="id"
                dataSource={artifacts}
                pagination={artifacts.length > 8 ? { pageSize: 8, showSizeChanger: false } : false}
                columns={[
                  { title: '类型', dataIndex: 'type', width: 180 },
                  { title: '标题', dataIndex: 'title', ellipsis: true, render: (value) => value || '-' },
                  { title: '文件', dataIndex: 'path', ellipsis: true, render: (value) => value || '-' },
                ]}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无产物记录" />
            )}
          </div>
        </Space>
      ) : null}
    </Drawer>
  );
}

function defaultParamsForTemplate(template?: PipelineTemplate) {
  const schema = template?.params_schema || {};
  return Object.fromEntries(Object.entries(schema).map(([key, value]) => [key, value?.default]));
}

function templateName(templates: PipelineTemplate[], key: string) {
  return templates.find((item) => item.key === key)?.name || key;
}

function templateModeLabel(template: PipelineTemplate) {
  if (template.run_strategy === 'aggregate') return '多素材生成一个视频';
  if (template.input_scope === 'single_video' && template.output_cardinality === 'many') return '一个素材生成多个视频';
  if (template.input_scope === 'single_video' && template.output_cardinality === 'one') return '一个素材生成一个视频';
  return template.output_cardinality === 'many' ? '多产物' : '单产物';
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '等待',
    running: '运行中',
    succeeded: '完成',
    failed: '失败',
    canceled: '已取消',
  };
  return labels[status] || status;
}

function statusColor(status: string) {
  if (status === 'succeeded') return 'success';
  if (status === 'failed') return 'error';
  if (status === 'running') return 'processing';
  if (status === 'pending') return 'warning';
  return 'default';
}

function isActiveStatus(status: string) {
  return status === 'pending' || status === 'running';
}

function assetTypeLabel(type: string) {
  if (type === 'promo') return '推广视频';
  if (type === 'quality_cut') return '剧情精剪';
  if (type === 'highlight') return '高光片段';
  if (type === 'clip') return '手动片段';
  return type;
}
