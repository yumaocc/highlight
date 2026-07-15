import { CopyOutlined, DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { Button, Checkbox, Collapse, Empty, List, Modal, Select, Space, Tag, Typography, message } from 'antd';
import { useMemo, useState } from 'react';
import { VariantLinks } from '@/components/common/VariantLinks';
import type { Clip, GeneratedAsset, Trace } from '@/types/dashboard';

const { Text, Paragraph } = Typography;

type AssetOutputPanelProps = {
  assets: GeneratedAsset[];
  clips: Clip[];
  trace: Trace;
  summary: string;
};

export function AssetOutputPanel({ assets, clips, trace, summary }: AssetOutputPanelProps) {
  const [messageApi, contextHolder] = message.useMessage();
  const [preview, setPreview] = useState<{ title: string; url: string } | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [runFilter, setRunFilter] = useState<string>('all');
  const [selectedAssetIds, setSelectedAssetIds] = useState<number[]>([]);
  const promoVariants = trace.kind === 'promo' ? trace.data?.variants || [] : [];
  const filteredAssets = useMemo(
    () =>
      assets.filter((asset) => {
        if (typeFilter !== 'all' && asset.type !== typeFilter) return false;
        if (sourceFilter !== 'all' && String(asset.source_video_id || '') !== sourceFilter) return false;
        if (runFilter !== 'all' && String(asset.pipeline_run_id || '') !== runFilter) return false;
        return true;
      }),
    [assets, runFilter, sourceFilter, typeFilter],
  );
  const typeOptions = uniqueOptions(assets.map((asset) => ({ value: asset.type, label: assetTypeLabel(asset.type) })));
  const sourceOptions = uniqueOptions(
    assets
      .filter((asset) => asset.source_video_id)
      .map((asset) => ({ value: String(asset.source_video_id), label: asset.source_video_name || `素材 ${asset.source_video_id}` })),
  );
  const runOptions = uniqueOptions(
    assets
      .filter((asset) => asset.pipeline_run_id)
      .map((asset) => ({ value: String(asset.pipeline_run_id), label: `Run #${asset.pipeline_run_id}` })),
  );
  const hasAssets = filteredAssets.length > 0 || clips.length > 0 || promoVariants.length > 0 || (trace.kind === 'promo' && trace.data?.download_url);

  const content = (
    <>
      {contextHolder}
      <Paragraph className="summary-text">{summary}</Paragraph>
      {promoVariants.length > 0 && (
        <div className="asset-section">
          <Text strong>推广视频版本</Text>
          <VariantLinks
            variants={promoVariants}
            fallbackUrl={trace.kind === 'promo' ? trace.data?.download_url : undefined}
            onPreview={(item) => setPreview(item)}
          />
        </div>
      )}

      {assets.length > 0 && (
        <div className="asset-section">
          <Space direction="vertical" size={12} className="full-width">
            <Text strong>项目资产库</Text>
            <Space wrap>
              <Select
                size="small"
                value={typeFilter}
                style={{ minWidth: 140 }}
                options={[{ value: 'all', label: '全部类型' }, ...typeOptions]}
                onChange={setTypeFilter}
              />
              <Select
                size="small"
                value={sourceFilter}
                style={{ minWidth: 180 }}
                options={[{ value: 'all', label: '全部素材' }, ...sourceOptions]}
                onChange={setSourceFilter}
              />
              <Select
                size="small"
                value={runFilter}
                style={{ minWidth: 140 }}
                options={[{ value: 'all', label: '全部 Run' }, ...runOptions]}
                onChange={setRunFilter}
              />
              <Button
                size="small"
                disabled={!selectedAssetIds.length}
                href={publishHref(assets, selectedAssetIds)}
              >
                发布选中
              </Button>
            </Space>
          </Space>
          <List
            className="asset-list"
            dataSource={filteredAssets}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选下没有产物" /> }}
            renderItem={(asset) => {
              const promoCopy = asset.metadata?.promo_copy;
              const publishTags = Array.isArray(asset.metadata?.publish_tags) ? asset.metadata.publish_tags : [];
              return (
                <List.Item
                  actions={[
                    <Button
                      key="preview"
                      type="link"
                      icon={<PlayCircleOutlined />}
                      onClick={() =>
                        setPreview({
                          title: asset.title,
                          url: asset.download_url,
                        })
                      }
                    >
                      预览
                    </Button>,
                    <Button key="download" type="link" href={asset.download_url} icon={<DownloadOutlined />}>
                      下载
                    </Button>,
                    <Button
                      key="publish"
                      type="link"
                      href={`/publish?projectId=${asset.project_id}&assetIds=${asset.id}`}
                    >
                      发布
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={
                      <Checkbox
                        checked={selectedAssetIds.includes(asset.id)}
                        onChange={(event) => {
                          setSelectedAssetIds((current) =>
                            event.target.checked ? [...current, asset.id] : current.filter((id) => id !== asset.id),
                          );
                        }}
                      />
                    }
                    title={
                      <Space wrap>
                        <Tag color={asset.type === 'promo' ? 'blue' : 'green'}>
                          {assetTypeLabel(asset.type)}
                        </Tag>
                        {asset.metadata?.pipeline && <Tag>{asset.metadata.pipeline}</Tag>}
                        {asset.metadata?.review_cover?.enabled && (
                          <Tag color={asset.metadata.review_cover.mode === 'gpt-image-2' ? 'gold' : 'default'}>
                            首秒封面
                          </Tag>
                        )}
                        {asset.metadata?.outro_cta?.enabled && <Tag color="cyan">片尾引导</Tag>}
                        {asset.pipeline_run_id && <Tag color="purple">Run #{asset.pipeline_run_id}</Tag>}
                        <Text strong>{asset.title}</Text>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={6} className="full-width">
                        <Text type="secondary">{asset.description || asset.source_video_name || asset.output_path}</Text>
                        {promoCopy && (
                          <div className="asset-promo-copy">
                            <Space align="start" className="full-width" size={8}>
                              <Tag color="orange">{asset.metadata?.promo_copy_title || '宣传文案'}</Tag>
                              <Space direction="vertical" size={4} className="full-width">
                                <Paragraph className="asset-promo-copy-text">{promoCopy}</Paragraph>
                                {publishTags.length > 0 && (
                                  <Space wrap size={[4, 4]}>
                                    {publishTags.map((tag: string) => (
                                      <Tag key={tag}>{tag}</Tag>
                                    ))}
                                  </Space>
                                )}
                              </Space>
                              <Button
                                size="small"
                                type="text"
                                icon={<CopyOutlined />}
                                onClick={() => copyText(promoCopy, messageApi)}
                              />
                            </Space>
                          </div>
                        )}
                        <Text type="secondary">
                          {asset.source_video_name || '未知素材'}
                          {asset.pipeline_step_id ? ` · Step #${asset.pipeline_step_id}` : ''}
                          {asset.metadata?.review_cover?.enabled ? ` · ${coverModeLabel(asset.metadata.review_cover.mode)}` : ''}
                          {asset.metadata?.outro_cta?.enabled ? ` · ${outroModeLabel(asset.metadata.outro_cta.mode)}` : ''}
                        </Text>
                      </Space>
                    }
                  />
                </List.Item>
              );
            }}
          />
        </div>
      )}

      {!assets.length && clips.length > 0 ? (
        <List
          className="asset-list"
          dataSource={clips}
          renderItem={(clip) => (
            <List.Item
              actions={[
                <Button
                  key="preview"
                  type="link"
                  icon={<PlayCircleOutlined />}
                  onClick={() =>
                    setPreview({
                      title: `高光片段 ${Number(clip.start_seconds).toFixed(2)}s - ${Number(clip.end_seconds).toFixed(2)}s`,
                      url: `/api/clips/${clip.id}/download`,
                    })
                  }
                >
                  预览
                </Button>,
                <Button key="download" type="link" href={`/api/clips/${clip.id}/download`} icon={<DownloadOutlined />}>
                  下载
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Tag color="green">高光片段</Tag>
                    <Text strong>
                      {Number(clip.start_seconds).toFixed(2)}s - {Number(clip.end_seconds).toFixed(2)}s
                    </Text>
                  </Space>
                }
                description={clip.reason || '手动导出'}
              />
            </List.Item>
          )}
        />
      ) : !hasAssets ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="生成后的视频产物会出现在这里" />
      ) : null}
      <Modal
        title={preview?.title || '视频预览'}
        open={Boolean(preview)}
        footer={null}
        width={860}
        destroyOnClose
        onCancel={() => setPreview(null)}
      >
        {preview && (
          <video
            className="asset-preview-video"
            src={preview.url}
            controls
            autoPlay
            playsInline
          />
        )}
      </Modal>
    </>
  );

  return (
    <Collapse
      className="focus-collapse"
      defaultActiveKey={['asset-output']}
      items={[
        {
          key: 'asset-output',
          label: '产物',
          children: content,
        },
      ]}
    />
  );
}

function assetTypeLabel(type: string) {
  if (type === 'promo') return '推广视频';
  if (type === 'clip') return '手动片段';
  if (type === 'highlight') return '高光片段';
  if (type === 'quality_cut') return '剧情精剪';
  return type;
}

function coverModeLabel(mode?: string) {
  if (mode === 'gpt-image-2') return 'GPT Image 2 封面';
  if (mode === 'fallback_text_card') return '文字兜底封面';
  return '首秒封面';
}

function outroModeLabel(mode?: string) {
  if (mode === 'gpt-image-2') return 'GPT Image 2 片尾引导';
  if (mode === 'fallback_text_card') return '文字兜底片尾引导';
  return '片尾引导';
}

function uniqueOptions(options: { value: string; label: string }[]) {
  const seen = new Set<string>();
  return options.filter((option) => {
    if (seen.has(option.value)) return false;
    seen.add(option.value);
    return true;
  });
}

function publishHref(assets: GeneratedAsset[], selectedAssetIds: number[]) {
  const selected = assets.filter((asset) => selectedAssetIds.includes(asset.id));
  const projectId = selected[0]?.project_id;
  if (!projectId) return '/publish';
  return `/publish?projectId=${projectId}&assetIds=${selected.map((asset) => asset.id).join(',')}`;
}

async function copyText(text: string, messageApi: ReturnType<typeof message.useMessage>[0]) {
  try {
    await navigator.clipboard.writeText(text);
    messageApi.success('已复制宣传文案');
  } catch {
    messageApi.error('复制失败，请手动选中文案复制');
  }
}
