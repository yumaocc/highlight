import { Card, Typography } from 'antd';
import { VariantLinks } from '@/components/common/VariantLinks';
import type { Trace } from '@/types/dashboard';

const { Paragraph } = Typography;

export function AutoResultCard({ summary, trace }: { summary: string; trace: Trace }) {
  return (
    <Card title="自动生成结果">
      <Paragraph className="summary-text">{summary}</Paragraph>
      {trace.kind === 'promo' && <VariantLinks variants={trace.data?.variants || []} fallbackUrl={trace.data?.download_url} />}
    </Card>
  );
}
