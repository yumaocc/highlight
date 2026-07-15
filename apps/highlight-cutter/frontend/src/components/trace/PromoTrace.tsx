import { DownloadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Divider, Empty, Flex, List, Row, Space, Tabs, Tag, Typography } from 'antd';
import { formatScore } from '@/utils/format';
import { TraceColumn } from './TraceColumn';

const { Text, Paragraph } = Typography;

export function PromoTrace({ result }: { result: any }) {
  const variants = result.variants || [];
  const structure = result.structure || [];
  const editReview = result.edit_review || {};
  if (!variants.length && !structure.length) return <Empty description={result.error || '没有选出推广片段'} />;
  return (
    <Space direction="vertical" size={12} className="full-width">
      <Alert
        type="success"
        showIcon
        message={result.title || '推广视频结构'}
        description={
          <Space direction="vertical" size={4}>
            <Text>候选片段：{Number(result.candidate_count || 0)} 个</Text>
            {editReview.mode && <Text>审片模式：{editReview.mode}</Text>}
            {editReview.selected_candidate_ids && <Text>最终候选：{editReview.selected_candidate_ids.join('、')}</Text>}
            {editReview.storyline && <Text>故事线：{editReview.storyline}</Text>}
            {result.opening && (
              <Text>
                开头：{result.opening.title || ''}
                {result.opening.subtitle ? ` / ${result.opening.subtitle}` : ''}
              </Text>
            )}
            {result.ending && (
              <Text>
                结尾：{result.ending.title || ''}
                {result.ending.subtitle ? ` / ${result.ending.subtitle}` : ''}
              </Text>
            )}
          </Space>
        }
      />
      <Tabs
        items={[
          {
            key: 'versions',
            label: '推广版本',
            children: <PromoVersions variants={variants} />,
          },
          {
            key: 'beats',
            label: '节拍明细',
            children: <PromoBeats structure={structure} />,
          },
          {
            key: 'review',
            label: '双模型审片',
            children: <PromoReview editReview={editReview} />,
          },
        ]}
      />
    </Space>
  );
}

function PromoVersions({ variants }: { variants: any[] }) {
  return (
    <List
      dataSource={variants}
      renderItem={(variant: any) => (
        <List.Item>
          <Card size="small" className="trace-card">
            <Flex justify="space-between" gap={12} wrap="wrap">
              <div>
                <Text strong>{variant.label || variant.key || '推广版本'}</Text>
                <Paragraph className="compact-paragraph">{variant.title || '未生成标题'}</Paragraph>
              </div>
              <Button type="link" href={variant.download_url} icon={<DownloadOutlined />}>
                下载{variant.label || '推广视频'}
              </Button>
            </Flex>
            <Space wrap>
              <Tag>节拍 {(variant.structure || []).length}</Tag>
              <Tag color="cyan">开头 {formatScore(variant.scores?.opening_strength)}</Tag>
              <Tag color="purple">悬念 {formatScore(variant.scores?.cliffhanger_strength)}</Tag>
            </Space>
            {variant.opening && (
              <Paragraph className="compact-paragraph">
                开头：{variant.opening.title || ''}
                {variant.opening.subtitle ? ` / ${variant.opening.subtitle}` : ''}
              </Paragraph>
            )}
            {variant.ending && (
              <Paragraph className="compact-paragraph">
                结尾：{variant.ending.title || ''}
                {variant.ending.subtitle ? ` / ${variant.ending.subtitle}` : ''}
              </Paragraph>
            )}
          </Card>
        </List.Item>
      )}
    />
  );
}

function PromoBeats({ structure }: { structure: any[] }) {
  return (
    <List
      dataSource={structure}
      renderItem={(item: any) => {
        const classification = item.classification || {};
        const transcript = item.transcript || {};
        const visual = item.visual || {};
        return (
          <List.Item>
            <Card size="small" className="trace-card">
              <Flex justify="space-between" gap={12}>
                <Text strong>
                  {item.role || 'promo'}: {item.video?.name || '未知视频'}
                </Text>
                <Text type="secondary">
                  候选 {item.candidate_id || '-'} · {Number(item.cut_start ?? item.start ?? 0).toFixed(2)}s - {Number(item.cut_end ?? item.end ?? 0).toFixed(2)}s · 分数 {item.score ?? 'N/A'}
                </Text>
              </Flex>
              <Divider className="compact-divider" />
              <Row gutter={12}>
                <TraceColumn title="Gemini 转写" text={transcript.text || transcript.error || '无转写内容'} />
                <TraceColumn
                  title="GPT 推广角色"
                  text={classification.reason || classification.error || '无分类说明'}
                  extra={[
                    classification.voiceover && `旁白：${classification.voiceover}`,
                    classification.opening_text && `开头文案：${classification.opening_text}`,
                    classification.ending_text && `结尾文案：${classification.ending_text}`,
                    `开头强度：${formatScore(classification.opening_strength)} · 悬念强度：${formatScore(classification.cliffhanger_strength)}`,
                  ].filter(Boolean)}
                />
                <TraceColumn title="Gemini 画面判断" text={visual.summary || visual.error || '无视觉复评内容'} />
              </Row>
            </Card>
          </List.Item>
        );
      }}
    />
  );
}

function PromoReview({ editReview }: { editReview: any }) {
  return (
    <Space direction="vertical" size={12} className="full-width">
      <TraceColumn
        title="GPT 草案"
        text={editReview.gpt_draft?.storyline || editReview.gpt_draft?.error || '暂无 GPT 草案'}
        extra={[
          editReview.gpt_draft?.selected_candidate_ids && `候选：${editReview.gpt_draft.selected_candidate_ids.join('、')}`,
          editReview.gpt_draft?.continuity_notes && `连续性：${editReview.gpt_draft.continuity_notes}`,
        ].filter(Boolean)}
      />
      <TraceColumn
        title="Gemini 审核"
        text={editReview.gemini_review?.reason || editReview.gemini_review?.error || '暂无 Gemini 审核'}
        extra={[
          editReview.gemini_review?.suggested_candidate_ids && `建议候选：${editReview.gemini_review.suggested_candidate_ids.join('、')}`,
          editReview.gemini_review?.continuity_risks && `风险：${editReview.gemini_review.continuity_risks.join('；')}`,
        ].filter(Boolean)}
      />
      <TraceColumn
        title="GPT 最终决定"
        text={editReview.gpt_final?.decision_reason || editReview.gpt_final?.error || '暂无最终决定'}
        extra={[
          editReview.gpt_final?.selected_candidate_ids && `最终候选：${editReview.gpt_final.selected_candidate_ids.join('、')}`,
          editReview.gpt_final?.continuity_notes && `连续性：${editReview.gpt_final.continuity_notes}`,
        ].filter(Boolean)}
      />
    </Space>
  );
}
