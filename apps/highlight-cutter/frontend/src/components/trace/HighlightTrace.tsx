import { Card, Divider, Empty, Flex, List, Row, Typography } from 'antd';
import { TraceColumn } from './TraceColumn';

const { Text } = Typography;

export function HighlightTrace({ items }: { items: any[] }) {
  if (!items.length) return <Empty description="没有生成结果" />;
  return (
    <List
      className="trace-list"
      dataSource={items}
      renderItem={(item) => {
        const ai = item.ai || {};
        const transcript = ai.transcript || {};
        const textReview = ai.text_review || {};
        const visualReview = ai.visual_review || {};
        return (
          <List.Item>
            <Card size="small" className="trace-card">
              <Flex justify="space-between" gap={12}>
                <Text strong ellipsis>
                  {item.video_name || '未知视频'}
                </Text>
                <Text type="secondary">
                  {Number(item.start || 0).toFixed(2)}s - {Number(item.end || 0).toFixed(2)}s · 分数 {item.score ?? 'N/A'}
                </Text>
              </Flex>
              <Divider className="compact-divider" />
              <Row gutter={12}>
                <TraceColumn title="Gemini 转写" text={transcript.text || transcript.error || '无转写内容'} />
                <TraceColumn
                  title="GPT 台词分析"
                  text={textReview.summary || textReview.error || '无分析内容'}
                  extra={[textReview.hook && `Hook：${textReview.hook}`, textReview.continuity && `连贯性：${textReview.continuity}`].filter(Boolean)}
                />
                <TraceColumn
                  title="Gemini 视觉复评"
                  text={visualReview.summary || visualReview.error || '无视觉复评内容'}
                  extra={visualReview.continuity_risk ? [`连贯性风险：${visualReview.continuity_risk}`] : []}
                />
              </Row>
            </Card>
          </List.Item>
        );
      }}
    />
  );
}
