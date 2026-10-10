import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [
    sveltekit({
      adapter: adapter({ fallback: '404.html' }),
      // GitHub Pages serves the site below /<repository>; CI sets BASE_PATH accordingly.
      paths: { base: (process.env.BASE_PATH ?? '') as '' | `/${string}` },
      prerender: { handleHttpError: 'warn' }
    })
  ],
  server: { fs: { allow: ['..'] } },
  test: { include: ['src/**/*.test.ts'], environment: 'node' }
});
