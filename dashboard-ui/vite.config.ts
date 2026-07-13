import path from 'node:path';
import {fileURLToPath} from 'node:url';
import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(root, 'src'),
    },
  },
  esbuild: {
    jsx: 'transform',
    jsxFactory: '_HermesReact.createElement',
    jsxFragment: '_HermesReact.Fragment',
    jsxInject: "import _HermesReact from 'react'",
  },
  build: {
    lib: {
      entry: path.resolve(root, 'src/plugin-entry.tsx'),
      name: 'IrodoriTTSHermesPlugin',
      formats: ['iife'],
      fileName: () => 'index.js',
    },
    outDir: path.resolve(root, '../dashboard/dist'),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      external: ['react'],
      output: {
        globals: {
          react: 'window.__HERMES_PLUGIN_SDK__.React',
        },
        assetFileNames: asset => asset.name?.endsWith('.css') ? 'style.css' : 'assets/[name][extname]',
      },
    },
  },
});
