import { DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { Button, Space } from 'antd';

type PreviewPayload = {
  title: string;
  url: string;
};

export function VariantLinks({
  variants,
  fallbackUrl,
  onPreview,
}: {
  variants: any[];
  fallbackUrl?: string;
  onPreview?: (payload: PreviewPayload) => void;
}) {
  if (variants.length) {
    return (
      <Space wrap>
        {variants.map((variant) => (
          <Space.Compact key={variant.key}>
            {onPreview && (
              <Button
                icon={<PlayCircleOutlined />}
                onClick={() =>
                  onPreview({
                    title: variant.label || variant.key || '推广视频',
                    url: variant.download_url,
                  })
                }
              >
                预览
              </Button>
            )}
            <Button href={variant.download_url} icon={<DownloadOutlined />}>
              下载{variant.label || variant.key}
            </Button>
          </Space.Compact>
        ))}
      </Space>
    );
  }

  return fallbackUrl ? (
    <Space.Compact>
      {onPreview && (
        <Button icon={<PlayCircleOutlined />} onClick={() => onPreview({ title: '推广视频', url: fallbackUrl })}>
          预览
        </Button>
      )}
      <Button href={fallbackUrl} icon={<DownloadOutlined />}>
        下载推广视频
      </Button>
    </Space.Compact>
  ) : null;
}
