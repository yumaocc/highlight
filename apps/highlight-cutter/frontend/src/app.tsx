import { App, ConfigProvider, theme } from 'antd';
import type { ReactNode } from 'react';
import './global.css';

export function rootContainer(container: ReactNode) {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#0f766e',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        },
      }}
    >
      <App>{container}</App>
    </ConfigProvider>
  );
}
