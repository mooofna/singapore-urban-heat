import source from '../../../../docs/methodology.md?raw';
import { headings, renderMarkdown } from '#lib/markdown.ts';

export const load = () => {
  const html = renderMarkdown(source);
  return { html, toc: headings(html) };
};
