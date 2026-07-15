import { defineConfig } from '@umijs/max';

export default defineConfig({
  npmClient: 'pnpm',
  outputPath: 'dist',
  publicPath: '/',
  history: {
    type: 'browser',
  },
  routes: [
    {
      path: '/',
      component: '@/pages/auto-publish/index',
    },
    {
      path: '/manual',
      component: '@/pages/index',
    },
    {
      path: '/publish',
      component: '@/pages/publish',
    },
    {
      path: '/content-promotion',
      component: '@/pages/content-promotion/index',
    },
    {
      path: '/published',
      component: '@/pages/published/index',
    },
    {
      path: '/auto-publish',
      component: '@/pages/auto-publish/index',
    },
    {
      path: '/workflow',
      component: '@/pages/workflow/index',
    },
    {
      path: '/accounts/login',
      component: '@/pages/accounts/login',
    },
    {
      path: '/accounts',
      component: '@/pages/accounts',
    },
    {
      path: '/settings',
      component: '@/pages/settings/index',
    },
  ],
  proxy: {
    '/api': {
      target: process.env.HIGHLIGHT_SERVICE_URL || 'http://127.0.0.1:8765',
      changeOrigin: true,
    },
    '/publish-api': {
      target: process.env.PUBLISH_SERVICE_URL || 'http://127.0.0.1:8770',
      changeOrigin: true,
      pathRewrite: { '^/publish-api': '/api' },
    },
  },
  title: 'Highlight Console',
});
