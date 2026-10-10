import katex from 'katex';
import { Marked } from 'marked';

/**
 * Render Markdown with TeX math ($...$ inline, $$...$$ display) to HTML.
 * Runs at build time only (prerendered pages), so KaTeX never ships to the browser.
 */
export function renderMarkdown(source: string): string {
  const math: string[] = [];
  const stash = (html: string) => `@@MATH${math.push(html) - 1}@@`;
  let text = source.replace(/\$\$([\s\S]+?)\$\$/g, (_, tex: string) =>
    stash(katex.renderToString(tex.trim(), { displayMode: true, throwOnError: true }))
  );
  text = text.replace(/(?<![\\\w$])\$([^$\n]+?)\$/g, (_, tex: string) =>
    stash(katex.renderToString(tex, { throwOnError: true }))
  );
  const marked = new Marked({ gfm: true });
  marked.use({
    renderer: {
      heading({ tokens, depth }) {
        const inner = this.parser.parseInline(tokens);
        const plain = inner.replace(/<[^>]+>/g, '');
        const id = plain
          .toLowerCase()
          .replace(/@@math\d+@@/g, '')
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/^-|-$/g, '');
        return `<h${depth} id="${id}">${inner}</h${depth}>\n`;
      }
    }
  });
  const html = marked
    .parse(text, { async: false })
    .replace(/<table>/g, '<div class="table-wrap" tabindex="0" role="region" aria-label="Table">')
    .replace(/<\/table>/g, '</table></div>');
  return html
    .replace(/@@MATH(\d+)@@/g, (_, i: string) => math[Number(i)] ?? '')
    .replace(/<span class="katex-display">/g, '<span class="katex-display" tabindex="0">');
}

/** Second-level headings with their anchor ids, for a table of contents. */
export function headings(html: string): { id: string; text: string }[] {
  return [...html.matchAll(/<h2 id="([^"]+)">(.*?)<\/h2>/g)].map((m) => ({
    id: m[1] ?? '',
    text: (m[2] ?? '').replace(/<[^>]+>/g, '')
  }));
}
