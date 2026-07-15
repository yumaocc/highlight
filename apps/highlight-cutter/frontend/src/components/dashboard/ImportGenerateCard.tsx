import { PlayCircleOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Card, Col, Row, Select, Space, Typography, Upload } from 'antd';
import { ENGINES, MODES } from '@/constants/options';
import type { TaskStatus } from '@/types/dashboard';
import { StatusTag } from '@/components/common/StatusTag';

const { Dragger } = Upload;
const { Text } = Typography;

type ImportGenerateCardProps = {
  busy: boolean;
  mode: string;
  engine: string;
  uploadHint: string;
  status: TaskStatus;
  onModeChange: (value: string) => void;
  onEngineChange: (value: string) => void;
  onUploadFiles: (files: File[]) => void;
  onRunHighlights: () => void;
  onRunPromo: () => void;
};

export function ImportGenerateCard({
  busy,
  mode,
  engine,
  uploadHint,
  status,
  onModeChange,
  onEngineChange,
  onUploadFiles,
  onRunHighlights,
  onRunPromo,
}: ImportGenerateCardProps) {
  return (
    <Card title="导入与生成" extra={<StatusTag status={status} />}>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={14}>
          <Dragger
            multiple
            accept="video/*"
            showUploadList={false}
            disabled={busy}
            beforeUpload={(file, fileList) => {
              if (file.uid === fileList[0]?.uid) onUploadFiles(fileList as unknown as File[]);
              return false;
            }}
          >
            <p className="upload-title">
              <UploadOutlined /> 上传一组视频
            </p>
            <p className="ant-upload-text">点击选择文件或拖拽到这里</p>
            <p className="ant-upload-hint">{uploadHint}</p>
          </Dragger>
        </Col>
        <Col xs={24} md={10}>
          <Space direction="vertical" size={12} className="full-width">
            <div>
              <Text type="secondary">生成类型</Text>
              <Select value={mode} onChange={onModeChange} options={MODES} className="full-width" />
            </div>
            <div>
              <Text type="secondary">分析引擎</Text>
              <Select value={engine} onChange={onEngineChange} options={ENGINES} className="full-width" />
            </div>
            <Button
              type="primary"
              block
              loading={busy}
              icon={<PlayCircleOutlined />}
              onClick={mode === 'promo' ? onRunPromo : onRunHighlights}
            >
              {mode === 'promo' ? '生成推广视频' : '生成高光视频'}
            </Button>
          </Space>
        </Col>
      </Row>
    </Card>
  );
}
