import { Col, Typography } from 'antd';

const { Text, Paragraph } = Typography;

export function TraceColumn({ title, text, extra = [] }: { title: string; text: string; extra?: string[] }) {
  return (
    <Col xs={24} md={8}>
      <div className="trace-column">
        <Text strong>{title}</Text>
        <Paragraph className="trace-text">{text}</Paragraph>
        {extra.map((line, index) => (
          <Paragraph key={index} className="trace-extra">
            {line}
          </Paragraph>
        ))}
      </div>
    </Col>
  );
}
