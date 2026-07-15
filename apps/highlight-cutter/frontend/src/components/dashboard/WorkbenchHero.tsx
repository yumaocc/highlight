import { FolderOpenOutlined, UploadOutlined } from '@ant-design/icons';
import { App, Button, Col, Row, Space, Typography, Upload } from 'antd';

const { Dragger } = Upload;
const { Text, Title } = Typography;
const VIDEO_EXTENSIONS = ['.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi'];
const VIDEO_ACCEPT = 'video/*,.mp4,.mov,.m4v,.mkv,.webm,.avi';

type WorkbenchHeroProps = {
  busy: boolean;
  uploadHint: string;
  onUploadFiles: (files: File[]) => void;
};

function isVideoFile(file: File) {
  const fileName = file.name.toLowerCase();
  return VIDEO_EXTENSIONS.some((extension) => fileName.endsWith(extension));
}

export function WorkbenchHero({
  busy,
  uploadHint,
  onUploadFiles,
}: WorkbenchHeroProps) {
  const { message } = App.useApp();

  function handleSelectedFiles(file: File, fileList: File[]) {
    if ((file as File & { uid?: string }).uid !== (fileList[0] as File & { uid?: string } | undefined)?.uid) return;

    const videoFiles = fileList.filter(isVideoFile);
    if (!videoFiles.length) {
      message.warning('文件夹中没有找到支持的视频文件');
      return;
    }
    onUploadFiles(videoFiles);
  }

  return (
    <section className="workbench-hero">
      <Row gutter={[24, 24]} align="stretch">
        <Col xs={24}>
          <div className="upload-workspace">
            <div className="upload-toolbar">
              <div className="section-kicker">素材导入</div>
              <Space wrap>
                <Upload
                  directory
                  multiple
                  accept={VIDEO_ACCEPT}
                  showUploadList={false}
                  disabled={busy}
                  beforeUpload={(file, fileList) => {
                    handleSelectedFiles(file as unknown as File, fileList as unknown as File[]);
                    return false;
                  }}
                >
                  <Button icon={<FolderOpenOutlined />} disabled={busy}>
                    选择文件夹
                  </Button>
                </Upload>
              </Space>
            </div>
            <Dragger
              multiple
              accept={VIDEO_ACCEPT}
              showUploadList={false}
              disabled={busy}
              beforeUpload={(file, fileList) => {
                handleSelectedFiles(file as unknown as File, fileList as unknown as File[]);
                return false;
              }}
            >
              <div className="upload-icon-wrap">
                <UploadOutlined />
              </div>
              <Title level={4} className="upload-heading">
                上传短剧素材
              </Title>
              <Text className="upload-subtitle">拖入视频或点击选择文件</Text>
              <Text type="secondary" className="upload-hint">
                {uploadHint}
              </Text>
            </Dragger>
          </div>
        </Col>
      </Row>
    </section>
  );
}
