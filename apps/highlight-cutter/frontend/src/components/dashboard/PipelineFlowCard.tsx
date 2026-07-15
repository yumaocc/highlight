import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Descriptions, Drawer, Empty, Form, InputNumber, Select, Space, Switch, Table, Tag, Timeline, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import type { PipelineArtifact, PipelineRun, PipelineTemplate, Video } from '@/types/dashboard';

const { Paragraph, Text } = Typography;

type PipelineFlowCardProps = {
  busy: boolean;
  videos: Video[];
  templates: PipelineTemplate[];
  runs: PipelineRun[];
  artifacts: PipelineArtifact[];
  selectedRun: PipelineRun | null;
  selectedVideoIds: number[];
  onSelectedVideoIdsChange: (ids: number[]) => void;
  onRunPipeline: (templateKey: string, params: Record<string, any>, enqueue: boolean) => void;
  onRefreshRuns: () => void;
  onOpenRun: (run: PipelineRun) => void;
  onCloseRun: () => void;
};

export function PipelineFlowCard({
  busy,
  videos,
  templates,
  runs,
  artifacts,
  selectedRun,
  selectedVideoIds,
  onSelectedVideoIdsChange,
  onRunPipeline,
  onRefreshRuns,
  onOpenRun,
  onCloseRun,
}: PipelineFlowCardProps) {
  const [form] = Form.useForm<{ template_key: string; params?: Record<string, any> }>();
  const [templateKey, setTemplateKey] = useState<string | undefined>(templates[0]?.key);
  const [enqueue, setEnqueue] = useState(false);
  const selectedTemplate = templates.find((item) => item.key === templateKey) || templates[0];
  const paramsSchema = selectedTemplate?.params_schema || {};
  const allVideoIds = useMemo(() => videos.map((video) => video.id), [videos]);
  const allSelected = Boolean(videos.length) && selectedVideoIds.length === allVideoIds.length;
  const runStrategy = selectedTemplate?.run_strategy || 'per_source';
  const runCountHint = runStrategy === 'aggregate'
    ? `将创建 1 个总剪任务`
    : `将创建 ${selectedVideoIds.length} 个任务`;
  const qualityReview = useMemo(() => buildQualityReview(artifacts), [artifacts]);

  useEffect(() => {
    const availableIds = new Set(allVideoIds);
    const nextSelectedIds = selectedVideoIds.filter((id) => availableIds.has(id));
    if (nextSelectedIds.length !== selectedVideoIds.length) onSelectedVideoIdsChange(nextSelectedIds);
  }, [allVideoIds, onSelectedVideoIdsChange, selectedVideoIds]);

  const runColumns: ColumnsType<PipelineRun> = [
    {
      title: '管道',
      dataIndex: 'template_key',
      width: 150,
      render: (value: string) => templateName(templates, value),
    },
    {
      title: '素材',
      dataIndex: 'source_video_name',
      ellipsis: true,
      render: (value: string, record) => {
        if ((record.source_count || 0) > 1) return `${record.source_count} 个素材`;
        return value || '未绑定素材';
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string) => <Tag color={statusColor(value)}>{statusLabel(value)}</Tag>,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 90,
      render: (value: number) => `${value || 0}%`,
    },
    {
      title: '当前步骤',
      dataIndex: 'current_step',
      width: 160,
      render: (value: string) => value || '-',
    },
    {
      title: '操作',
      width: 90,
      render: (_, record) => (
        <Button type="link" onClick={() => onOpenRun(record)}>
          详情
        </Button>
      ),
    },
  ];

  const timelineItems = useMemo(
    () =>
      (selectedRun?.steps || []).map((step) => ({
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
            {step.step_key === 'generate_review_cover' && <ReviewPackStepSummary output={step.output} kind="cover" />}
            {step.step_key === 'generate_outro_cta' && <ReviewPackStepSummary output={step.output} kind="outro" />}
          </Space>
        ),
      })),
    [selectedRun],
  );

  function submit(values: { template_key: string; params?: Record<string, any> }) {
    onRunPipeline(values.template_key, values.params || {}, enqueue || runStrategy === 'aggregate');
  }

  return (
    <Card
      title="管道生成"
      extra={
        <Button icon={<ReloadOutlined />} onClick={onRefreshRuns}>
          刷新记录
        </Button>
      }
    >
      <Space direction="vertical" size={16} className="full-width">
        <Form
          form={form}
          layout="vertical"
          initialValues={{ template_key: selectedTemplate?.key }}
          onFinish={submit}
        >
          <Space direction="vertical" size={12} className="full-width">
            <Form.Item name="template_key" label="管道模板" rules={[{ required: true, message: '请选择管道模板' }]}>
              <Select
                placeholder="选择生成模式"
                options={templates.map((item) => ({
                  value: item.key,
                  label: `${item.name} · ${templateModeLabel(item)}`,
                }))}
                onChange={(value) => setTemplateKey(value)}
              />
            </Form.Item>
            {selectedTemplate?.description && <Paragraph className="compact-paragraph">{selectedTemplate.description}</Paragraph>}
            <div className="pipeline-source-toolbar">
              <Text type="secondary">
                已选 {selectedVideoIds.length} / {videos.length} 个素材，{runCountHint}
              </Text>
              <Space>
                <Button
                  size="small"
                  onClick={() => onSelectedVideoIdsChange(allVideoIds)}
                  disabled={!videos.length || allSelected || busy}
                >
                  全选
                </Button>
                <Button
                  size="small"
                  onClick={() => onSelectedVideoIdsChange([])}
                  disabled={!selectedVideoIds.length || busy}
                >
                  清空
                </Button>
              </Space>
            </div>
            <Select
              mode="multiple"
              placeholder="选择要进入管道的素材"
              value={selectedVideoIds}
              options={videos.map((video) => ({ value: video.id, label: video.name }))}
              onChange={onSelectedVideoIdsChange}
            />
            {Object.entries(paramsSchema).map(([key, config]) => (
              <Form.Item
                key={key}
                name={['params', key]}
                label={config.label || key}
                initialValue={config.default}
              >
                {config.type === 'select' ? (
                  <Select
                    options={(config.options || []).map((option: string) => ({ value: option, label: paramOptionLabel(option) }))}
                  />
                ) : (
                  <InputNumber className="full-width" min={0} />
                )}
              </Form.Item>
            ))}
            <Space>
              <Switch checked={enqueue || runStrategy === 'aggregate'} onChange={setEnqueue} disabled={runStrategy === 'aggregate'} />
              <Text type="secondary">{runStrategy === 'aggregate' ? '多素材总剪固定加入队列后台执行' : '加入队列后台执行'}</Text>
            </Space>
            <Button
              type="primary"
              htmlType="submit"
              icon={<PlayCircleOutlined />}
              loading={busy}
              disabled={!selectedVideoIds.length || !templates.length}
            >
              启动管道
            </Button>
          </Space>
        </Form>

        <Table
          size="small"
          rowKey="id"
          columns={runColumns}
          dataSource={runs}
          pagination={runs.length > 5 ? { pageSize: 5, showSizeChanger: false } : false}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有管道运行记录" /> }}
        />
      </Space>

      <Drawer title="管道运行详情" open={Boolean(selectedRun)} onClose={onCloseRun} width={760} destroyOnClose>
        {selectedRun && (
          <Space direction="vertical" size={16} className="full-width">
            <Descriptions size="small" bordered column={1}>
              <Descriptions.Item label="模板">{templateName(templates, selectedRun.template_key)}</Descriptions.Item>
              <Descriptions.Item label="素材">
                {(selectedRun.source_count || 0) > 1
                  ? `${selectedRun.source_count} 个素材`
                  : selectedRun.source_video_name || selectedRun.source_video_id}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor(selectedRun.status)}>{statusLabel(selectedRun.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="进度">{selectedRun.progress || 0}%</Descriptions.Item>
              <Descriptions.Item label="错误">{selectedRun.error || '-'}</Descriptions.Item>
            </Descriptions>
            <div>
              <Text strong>步骤</Text>
              <Timeline className="pipeline-timeline" items={timelineItems} />
            </div>
            <div>
              <Text strong>提示词快照</Text>
              {selectedRun.prompt_snapshot?.prompts?.length ? (
                <Table
                  size="small"
                  rowKey="id"
                  dataSource={selectedRun.prompt_snapshot.prompts}
                  pagination={false}
                  columns={[
                    { title: 'Key', dataIndex: 'key', width: 180, ellipsis: true },
                    { title: '名称', dataIndex: 'name', width: 180, ellipsis: true },
                    { title: '内容', dataIndex: 'content', ellipsis: true },
                  ]}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无提示词快照" />
              )}
            </div>
            {qualityReview && <QualityReviewPanel review={qualityReview} />}
            <div>
              <Text strong>产物记录</Text>
              {artifacts.length ? (
                <Table
                  size="small"
                  rowKey="id"
                  dataSource={artifacts}
                  pagination={false}
                  columns={[
                    { title: '类型', dataIndex: 'type', width: 180 },
                    { title: '标题', dataIndex: 'title', ellipsis: true },
                    { title: '文件', dataIndex: 'path', ellipsis: true, render: (value: string) => value || '-' },
                  ]}
                />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无步骤产物" />
              )}
            </div>
          </Space>
        )}
      </Drawer>
    </Card>
  );
}

function QualityReviewPanel({ review }: { review: QualityReviewView }) {
  return (
    <Space direction="vertical" size={12} className="full-width">
      <Text strong>剧情精剪审片结果</Text>
      <Descriptions size="small" bordered column={2}>
        <Descriptions.Item label="模式">{review.mode || '-'}</Descriptions.Item>
        <Descriptions.Item label="保留策略">{paramOptionLabel(review.keep_policy || '-')}</Descriptions.Item>
        <Descriptions.Item label="预计成片">{formatSeconds(review.estimated_output_seconds)}</Descriptions.Item>
        <Descriptions.Item label="保留片段">{review.kept_segments.length}</Descriptions.Item>
        <Descriptions.Item label="说明" span={2}>{review.quality_notes || '-'}</Descriptions.Item>
      </Descriptions>
      {review.quality_risks.length ? (
        <Alert
          type="warning"
          showIcon
          message="质量风险"
          description={review.quality_risks.join('；')}
        />
      ) : null}
      {review.source_summaries.length ? (
        <Table
          size="small"
          rowKey="source_video_id"
          dataSource={review.source_summaries}
          pagination={false}
          columns={[
            { title: '素材', dataIndex: 'source_video_name', ellipsis: true },
            { title: '原时长', dataIndex: 'duration', width: 90, render: formatSeconds },
            { title: '保留时长', dataIndex: 'kept_seconds', width: 100, render: formatSeconds },
            { title: '保留比例', dataIndex: 'kept_ratio', width: 90, render: (value: number) => `${Math.round((value || 0) * 100)}%` },
            { title: '片段数', dataIndex: 'kept_count', width: 80 },
          ]}
        />
      ) : null}
      <Table
        size="small"
        rowKey={(record) => `${record.source_video_id}-${record.start}-${record.end}-${record.decision}`}
        dataSource={review.decisions}
        pagination={review.decisions.length > 8 ? { pageSize: 8, showSizeChanger: false } : false}
        columns={[
          { title: '素材', dataIndex: 'source_video_name', width: 150, ellipsis: true },
          { title: '时间段', width: 130, render: (_, record) => `${formatSeconds(record.start)} - ${formatSeconds(record.end)}` },
          { title: '决策', dataIndex: 'decision', width: 110, render: (value: string) => <Tag color={decisionColor(value)}>{decisionLabel(value)}</Tag> },
          { title: '角色', dataIndex: 'role', width: 120, ellipsis: true },
          { title: '原因', dataIndex: 'reason', ellipsis: true },
        ]}
      />
      {review.rejected_decisions.length ? (
        <Alert
          type="info"
          showIcon
          message={`${review.rejected_decisions.length} 条模型决策被拒绝`}
          description={review.rejected_decisions.map((item) => item.error).filter(Boolean).join('；')}
        />
      ) : null}
    </Space>
  );
}

function ReviewPackStepSummary({ output, kind }: { output?: any; kind: 'cover' | 'outro' }) {
  if (!output) return null;
  if (!output.enabled) {
    return <Text type="secondary">{kind === 'cover' ? '首秒封面未启用' : '片尾引导未启用'}</Text>;
  }
  const label = kind === 'cover' ? '首秒封面' : '片尾引导';
  return (
    <Space wrap size={6}>
      <Tag color={output.mode === 'gpt-image-2' ? 'gold' : 'default'}>{label}</Tag>
      <Text type="secondary">{output.mode || 'generated'}</Text>
      {output.segment_path && <Text type="secondary">{output.segment_path}</Text>}
    </Space>
  );
}

type QualityDecision = {
  source_video_id: number;
  source_video_name?: string;
  start: number;
  end: number;
  decision: string;
  role?: string;
  reason?: string;
};

type QualityReviewView = {
  mode?: string;
  keep_policy?: string;
  quality_notes?: string;
  estimated_output_seconds?: number;
  decisions: QualityDecision[];
  kept_segments: QualityDecision[];
  rejected_decisions: Array<{ error?: string }>;
  quality_risks: string[];
  source_summaries: Array<{
    source_video_id: number;
    source_video_name?: string;
    duration?: number;
    kept_seconds?: number;
    kept_ratio?: number;
    kept_count?: number;
  }>;
};

function buildQualityReview(artifacts: PipelineArtifact[]): QualityReviewView | null {
  const validated = artifacts.find((item) => item.type === 'validate_quality_edit_decisions')?.content;
  const modelReview = artifacts.find((item) => item.type === 'model_watch_quality_cut')?.content;
  if (!validated && !modelReview) return null;
  const content = validated || modelReview || {};
  const decisions = (content.decisions || []) as QualityDecision[];
  const keptSegments = (content.kept_segments || decisions.filter((item) => item.decision !== 'drop')) as QualityDecision[];
  return {
    mode: content.mode,
    keep_policy: content.keep_policy,
    quality_notes: content.quality_notes || content.summary,
    estimated_output_seconds: content.estimated_output_seconds,
    decisions,
    kept_segments: keptSegments,
    rejected_decisions: content.rejected_decisions || [],
    quality_risks: content.quality_risks || content.risks || [],
    source_summaries: content.source_summaries || [],
  };
}

function templateName(templates: PipelineTemplate[], key: string) {
  return templates.find((item) => item.key === key)?.name || key;
}

function templateModeLabel(template: PipelineTemplate) {
  if (template.run_strategy === 'aggregate') return '多对一';
  if (template.input_scope === 'single_video' && template.output_cardinality === 'many') return '一对多';
  if (template.input_scope === 'single_video' && template.output_cardinality === 'one') return '一对一';
  return template.output_cardinality === 'many' ? '多产物' : '单产物';
}

function paramOptionLabel(value: string) {
  const labels: Record<string, string> = {
    strict: '严格：只保留必要剧情',
    balanced: '平衡：保留必要剧情和有效过渡',
    loose: '宽松：只删除明显低质量片段',
  };
  return labels[value] || value;
}

function formatSeconds(value?: number) {
  const total = Math.max(0, Number(value || 0));
  const minutes = Math.floor(total / 60);
  const seconds = Math.round(total % 60);
  return minutes ? `${minutes}分${seconds}秒` : `${seconds}秒`;
}

function decisionLabel(value: string) {
  const labels: Record<string, string> = {
    keep_required: '必须保留',
    keep_optional: '建议保留',
    drop: '删除',
  };
  return labels[value] || value;
}

function decisionColor(value: string) {
  if (value === 'keep_required') return 'success';
  if (value === 'keep_optional') return 'processing';
  if (value === 'drop') return 'default';
  return 'warning';
}

function statusColor(status: string) {
  if (status === 'succeeded') return 'success';
  if (status === 'failed') return 'error';
  if (status === 'running') return 'processing';
  if (status === 'canceled') return 'default';
  return 'warning';
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '等待中',
    running: '运行中',
    succeeded: '已完成',
    failed: '失败',
    canceled: '已取消',
    skipped: '已跳过',
  };
  return labels[status] || status;
}
