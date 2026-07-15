import {
  BulbOutlined,
  EditOutlined,
  PictureOutlined,
  RocketOutlined,
  SendOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Form,
  Image,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout';
import { generateContentPromotion, getHealth } from '@/services/api';
import {
  createNotePublishTask,
  fallbackPlatforms,
  getPublishAccounts,
  getPublishTasks,
  type PublishAccount,
  type PublishTask,
} from '@/services/publish';
import type { ContentPromotionResult, Health } from '@/types/dashboard';
import { getErrorMessage } from '@/utils/errors';

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

type GenerateValues = {
  description: string;
  audience: string;
  tone: string;
};

type PublishValues = {
  platform: string;
  accountIds: string[];
  title: string;
  content: string;
  topics: string[];
};

const imageTextPlatforms = fallbackPlatforms.filter((item) => item.supportsImageText);

export default function ContentPromotionPage() {
  const { message } = App.useApp();
  const [generateForm] = Form.useForm<GenerateValues>();
  const [publishForm] = Form.useForm<PublishValues>();
  const [health, setHealth] = useState<Health | null>(null);
  const [accounts, setAccounts] = useState<PublishAccount[]>([]);
  const [result, setResult] = useState<ContentPromotionResult | null>(null);
  const [publishTask, setPublishTask] = useState<PublishTask | null>(null);
  const [generating, setGenerating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const selectedPlatform = Form.useWatch('platform', publishForm) || 'xiaohongshu';
  const filteredAccounts = useMemo(
    () => accounts.filter((account) => account.platform === selectedPlatform),
    [accounts, selectedPlatform],
  );

  useEffect(() => {
    Promise.all([getHealth().catch(() => null), getPublishAccounts().catch(() => [])]).then(([nextHealth, nextAccounts]) => {
      setHealth(nextHealth);
      setAccounts(nextAccounts);
    });
  }, []);

  useEffect(() => {
    publishForm.setFieldValue('accountIds', filteredAccounts.map((account) => String(account.id)));
  }, [filteredAccounts, publishForm]);

  useEffect(() => {
    if (!publishTask || !['pending', 'running'].includes(publishTask.status)) return;
    const timer = window.setInterval(async () => {
      const tasks = await getPublishTasks();
      const next = tasks.find((item) => item.id === publishTask.id);
      if (!next) return;
      setPublishTask(next);
      if (next.status === 'succeeded') message.success('图文内容发布完成');
      if (next.status === 'failed') message.error(next.message || '图文内容发布失败');
    }, 2500);
    return () => window.clearInterval(timer);
  }, [message, publishTask?.id, publishTask?.status]);

  async function generate(values: GenerateValues) {
    setGenerating(true);
    setPublishTask(null);
    try {
      const next = await generateContentPromotion({
        description: values.description,
        audience: values.audience,
        tone: values.tone,
        platform: selectedPlatform,
      });
      setResult(next);
      publishForm.setFieldsValue({
        title: next.title,
        content: next.content,
        topics: next.topics,
      });
      message.success('推广内容和宣传图已生成');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setGenerating(false);
    }
  }

  async function publish(values: PublishValues) {
    if (!result) return;
    setPublishing(true);
    try {
      const task = await createNotePublishTask({
        platform: values.platform,
        accountIds: values.accountIds,
        imagePaths: [result.image_path],
        title: values.title,
        content: values.content,
        topics: values.topics || [],
      });
      setPublishTask(task);
      message.success('图文发布任务已提交');
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setPublishing(false);
    }
  }

  return (
    <WorkspaceLayout
      health={health}
      title="内容推广"
      subtitle={<Text type="secondary">完善推广文案，生成宣传图片，并发布到已登录的平台账号。</Text>}
    >
      <Row gutter={[16, 16]} className="content-promotion-layout">
        <Col xs={24} xl={10}>
          <Card title={<Space><BulbOutlined />推广需求</Space>}>
            <Form
              form={generateForm}
              layout="vertical"
              initialValues={{ audience: '大众用户', tone: '专业、有吸引力、可信' }}
              onFinish={generate}
            >
              <Form.Item
                name="description"
                label="内容描述"
                rules={[{ required: true, min: 5, message: '请描述需要推广的内容' }]}
              >
                <TextArea rows={9} maxLength={6000} showCount placeholder="输入产品、活动、服务或内容亮点，以及希望用户采取的行动。" />
              </Form.Item>
              <Form.Item name="audience" label="目标人群">
                <Input placeholder="例如：25-35 岁职场用户" />
              </Form.Item>
              <Form.Item name="tone" label="表达风格">
                <Select
                  options={[
                    { value: '专业、有吸引力、可信', label: '专业可信' },
                    { value: '轻松、有亲和力、有分享感', label: '轻松分享' },
                    { value: '直接、有冲击力、行动导向', label: '强行动导向' },
                    { value: '克制、高级、有品牌质感', label: '品牌质感' },
                  ]}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<RocketOutlined />} loading={generating} block>
                完善内容并生成宣传图
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card title={<Space><PictureOutlined />推广成品</Space>}>
            {generating ? (
              <div className="content-promotion-loading"><Spin size="large" /><Text type="secondary">正在完善文案并生成图片...</Text></div>
            ) : result ? (
              <Form
                form={publishForm}
                layout="vertical"
                initialValues={{ platform: 'xiaohongshu', accountIds: [] }}
                onFinish={publish}
              >
                <div className="content-promotion-preview">
                  <Image src={result.image_url} alt="GPT Image 2 生成的宣传图片" />
                </div>
                {result.strategy && <Alert type="info" showIcon message="推广策略" description={result.strategy} />}
                <Form.Item name="title" label={<Space><EditOutlined />标题</Space>} rules={[{ required: true }]}>
                  <Input maxLength={40} showCount />
                </Form.Item>
                <Form.Item name="content" label="正文" rules={[{ required: true }]}>
                  <TextArea rows={7} maxLength={3000} showCount />
                </Form.Item>
                <Form.Item name="topics" label="话题">
                  <Select mode="tags" tokenSeparators={[',', '，']} maxCount={10} />
                </Form.Item>
                <Row gutter={12}>
                  <Col xs={24} md={9}>
                    <Form.Item name="platform" label="发布平台">
                      <Select options={imageTextPlatforms.map((item) => ({ value: item.key, label: item.name }))} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={15}>
                    <Form.Item name="accountIds" label="平台账号" rules={[{ required: true, message: '请选择发布账号' }]}>
                      <Select
                        mode="multiple"
                        placeholder="选择一个或多个账号"
                        options={filteredAccounts.map((account) => ({ value: String(account.id), label: account.name }))}
                      />
                    </Form.Item>
                  </Col>
                </Row>
                {!filteredAccounts.length && <Paragraph type="warning">该平台暂无可用账号，请先到“平台账号”完成登录。</Paragraph>}
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SendOutlined />}
                  loading={publishing}
                  disabled={!filteredAccounts.length}
                >
                  发布图文内容
                </Button>
                {publishTask && (
                  <Space className="content-promotion-task" wrap>
                    <Tag color={publishTask.status === 'failed' ? 'error' : publishTask.status === 'succeeded' ? 'success' : 'processing'}>
                      {publishTask.platform}
                    </Tag>
                    <Text>{publishTask.message || '发布任务已创建'}</Text>
                  </Space>
                )}
              </Form>
            ) : (
              <div className="content-promotion-empty">
                <PictureOutlined />
                <Text type="secondary">生成后的标题、正文、话题和宣传图会显示在这里。</Text>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </WorkspaceLayout>
  );
}
