import { Empty, Space, Tag, Typography } from 'antd';
import type { Trace, TraceMessage } from '@/types/dashboard';
import { formatScore } from '@/utils/format';

const { Text, Paragraph } = Typography;

export function TraceChat({ trace }: { trace: Trace }) {
  const messages = toMessages(trace);
  if (!messages.length) return <Empty description="生成后会在这里显示模型输出" />;

  return (
    <div className="trace-chat">
      {messages.map((message, index) => (
        <div key={`${message.title}-${index}`} className={`trace-message trace-message-${message.role}`}>
          <div className="trace-avatar">{message.role === 'system' ? 'S' : message.role === 'result' ? 'R' : 'AI'}</div>
          <div className="trace-bubble">
            <Space size={8} wrap className="trace-message-head">
              <Text strong>{message.title}</Text>
              {message.meta && <Tag>{message.meta}</Tag>}
            </Space>
            <Paragraph className="trace-message-body">{message.body}</Paragraph>
          </div>
        </div>
      ))}
    </div>
  );
}

function toMessages(trace: Trace): TraceMessage[] {
  if (trace.kind === 'empty') return [];
  if (trace.kind === 'messages') return compactMessages(trace.data || []);
  if (trace.kind === 'highlights') return highlightMessages(trace.data || []);
  if (trace.kind === 'promo') return promoMessages(trace.data || {});
  return [];
}

function highlightMessages(items: any[]): TraceMessage[] {
  return items.flatMap((item, index) => {
    const ai = item.ai || {};
    const transcript = ai.transcript || {};
    const textReview = ai.text_review || {};
    const visualReview = ai.visual_review || {};
    const range = `${Number(item.start || 0).toFixed(2)}s - ${Number(item.end || 0).toFixed(2)}s`;
    const videoName = item.video_name || `视频 ${index + 1}`;
    return compactMessages([
      {
        role: 'system',
        title: videoName,
        meta: `${range} · 分数 ${item.score ?? 'N/A'}`,
        body: item.status === 'exported' ? '已导出候选高光片段。' : item.error || item.reason || '候选片段已完成分析。',
      },
      {
        role: 'model',
        title: 'Gemini 转写',
        body: transcript.text || transcript.error,
      },
      {
        role: 'model',
        title: 'GPT 台词分析',
        body: joinLines([
          textReview.summary || textReview.error,
          textReview.hook && `Hook: ${textReview.hook}`,
          textReview.continuity && `连贯性: ${textReview.continuity}`,
        ]),
      },
      {
        role: 'model',
        title: 'Gemini 画面复评',
        body: joinLines([
          visualReview.summary || visualReview.error,
          visualReview.continuity_risk && `连贯性风险: ${visualReview.continuity_risk}`,
        ]),
      },
    ]);
  });
}

function promoMessages(result: any): TraceMessage[] {
  const messages: TraceMessage[] = [];
  const editReview = result.edit_review || {};
  const structure = result.structure || [];
  const variants = result.variants || [];

  messages.push({
    role: 'system',
    title: result.title || '推广视频结构',
    meta: `候选 ${Number(result.candidate_count || 0)} 个`,
    body: joinLines([
      editReview.storyline && `故事线: ${editReview.storyline}`,
      result.opening && `开头: ${result.opening.title || ''}${result.opening.subtitle ? ` / ${result.opening.subtitle}` : ''}`,
      result.ending && `结尾: ${result.ending.title || ''}${result.ending.subtitle ? ` / ${result.ending.subtitle}` : ''}`,
      result.model_review && `模型复核: ${result.model_review.decision || 'reviewed'}`,
      result.error,
    ]),
  });

  messages.push(
    ...compactMessages([
      {
        role: 'model',
        title: 'GPT 草案',
        body: joinLines([
          editReview.gpt_draft?.storyline || editReview.gpt_draft?.error,
          editReview.gpt_draft?.selected_candidate_ids && `候选: ${editReview.gpt_draft.selected_candidate_ids.join('、')}`,
          editReview.gpt_draft?.continuity_notes && `连续性: ${editReview.gpt_draft.continuity_notes}`,
        ]),
      },
      {
        role: 'model',
        title: 'Gemini 审核',
        body: joinLines([
          editReview.gemini_review?.reason || editReview.gemini_review?.error,
          editReview.gemini_review?.suggested_candidate_ids && `建议候选: ${editReview.gemini_review.suggested_candidate_ids.join('、')}`,
          editReview.gemini_review?.continuity_risks && `风险: ${editReview.gemini_review.continuity_risks.join('；')}`,
        ]),
      },
      {
        role: 'model',
        title: 'GPT 最终决定',
        body: joinLines([
          editReview.gpt_final?.decision_reason || editReview.gpt_final?.error,
          editReview.gpt_final?.selected_candidate_ids && `最终候选: ${editReview.gpt_final.selected_candidate_ids.join('、')}`,
          editReview.gpt_final?.continuity_notes && `连续性: ${editReview.gpt_final.continuity_notes}`,
        ]),
      },
    ]),
  );

  structure.forEach((item: any) => {
    const classification = item.classification || {};
    const transcript = item.transcript || {};
    const visual = item.visual || {};
    messages.push(
      ...compactMessages([
        {
          role: 'result',
          title: `${item.role || 'promo'} · ${item.video?.name || '未知视频'}`,
          meta: `${Number(item.cut_start ?? item.start ?? 0).toFixed(2)}s - ${Number(item.cut_end ?? item.end ?? 0).toFixed(2)}s`,
          body: joinLines([
            transcript.text && `转写: ${transcript.text}`,
            classification.reason && `角色判断: ${classification.reason}`,
            classification.voiceover && `旁白: ${classification.voiceover}`,
            classification.opening_text && `开头文案: ${classification.opening_text}`,
            classification.ending_text && `结尾文案: ${classification.ending_text}`,
            `开头强度: ${formatScore(classification.opening_strength)} · 悬念强度: ${formatScore(classification.cliffhanger_strength)}`,
            visual.summary && `画面判断: ${visual.summary}`,
            transcript.error || classification.error || visual.error,
          ]),
        },
      ]),
    );
  });

  variants.forEach((variant: any) => {
    messages.push({
      role: 'result',
      title: variant.label || variant.key || '推广版本',
      meta: `节拍 ${(variant.structure || []).length}`,
      body: joinLines([
        variant.title || '未生成标题',
        variant.opening && `开头: ${variant.opening.title || ''}${variant.opening.subtitle ? ` / ${variant.opening.subtitle}` : ''}`,
        variant.ending && `结尾: ${variant.ending.title || ''}${variant.ending.subtitle ? ` / ${variant.ending.subtitle}` : ''}`,
      ]),
    });
  });

  return compactMessages(messages);
}

function compactMessages(messages: Array<Partial<TraceMessage>>): TraceMessage[] {
  return messages
    .map((message) => ({
      role: message.role || 'model',
      title: message.title || '模型输出',
      meta: message.meta,
      body: (message.body || '').trim(),
    }))
    .filter((message) => message.body);
}

function joinLines(lines: Array<string | false | null | undefined>): string {
  return lines.filter(Boolean).join('\n');
}
