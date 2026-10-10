import { describe, expect, it } from 'vitest';
import { headings, renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
  it('renders inline and display math and anchors headings', () => {
    const html = renderMarkdown('## Surface $T_s$ heat\n\nInline $x^2$ and\n\n$$\na = b\n$$\n');
    expect(html).toContain('class="katex"');
    expect(html).toContain('katex-display');
    expect(headings(html)).toEqual([
      { id: 'surface-heat', text: expect.stringContaining('Surface') }
    ]);
  });

  it('leaves escaped and currency-like dollars alone', () => {
    const html = renderMarkdown('It costs US$5 today.');
    expect(html).not.toContain('katex');
  });
});
