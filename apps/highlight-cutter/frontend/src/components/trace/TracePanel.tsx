import { Empty } from 'antd';
import type { Trace } from '@/types/dashboard';
import { HighlightTrace } from './HighlightTrace';
import { PromoTrace } from './PromoTrace';

export function TracePanel({ trace }: { trace: Trace }) {
  if (trace.kind === 'empty') return <Empty description="暂无模型执行内容" />;
  if (trace.kind === 'highlights') return <HighlightTrace items={trace.data || []} />;
  if (trace.kind === 'promo') return <PromoTrace result={trace.data || {}} />;
  return null;
}
