// Colour scales. Sequential and diverging palettes are ColorBrewer schemes (Brewer, Penn State),
// which are colour-blind safe in the variants used here.

export const PALETTES = {
  // RdBu reversed: blue is cooler than the island, red hotter.
  diverging: [
    '#053061',
    '#2166ac',
    '#4393c3',
    '#92c5de',
    '#d1e5f0',
    '#f7f7f7',
    '#fddbc7',
    '#f4a582',
    '#d6604d',
    '#b2182b',
    '#67001f'
  ],
  heat: [
    '#ffffcc',
    '#ffeda0',
    '#fed976',
    '#feb24c',
    '#fd8d3c',
    '#fc4e2a',
    '#e31a1c',
    '#bd0026',
    '#800026'
  ],
  green: [
    '#ffffe5',
    '#f7fcb9',
    '#d9f0a3',
    '#addd8e',
    '#78c679',
    '#41ab5d',
    '#238443',
    '#006837',
    '#004529'
  ],
  blue: [
    '#f7fbff',
    '#deebf7',
    '#c6dbef',
    '#9ecae1',
    '#6baed6',
    '#4292c6',
    '#2171b5',
    '#08519c',
    '#08306b'
  ],
  purple: [
    '#f7f4f9',
    '#e7e1ef',
    '#d4b9da',
    '#c994c7',
    '#df65b0',
    '#e7298a',
    '#ce1256',
    '#980043',
    '#67001f'
  ],
  orange: [
    '#fff5eb',
    '#fee6ce',
    '#fdd0a2',
    '#fdae6b',
    '#fd8d3c',
    '#f16913',
    '#d94801',
    '#a63603',
    '#7f2704'
  ],
  grey: ['#f7f7f7', '#d9d9d9', '#bdbdbd', '#969696', '#737373', '#525252', '#252525']
} as const satisfies Record<string, readonly string[]>;

export type PaletteName = keyof typeof PALETTES;

/** Evenly spaced stops of a palette across a domain. */
export function stops(palette: readonly string[], domain: [number, number]): [number, string][] {
  const [lo, hi] = domain;
  const n = palette.length;
  return palette.map((c, k) => [lo + ((hi - lo) * k) / (n - 1), c]);
}

function hexToRgb(hex: string): [number, number, number] {
  const v = Number.parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

/** Colour of a value under linear interpolation between palette stops (clamped). */
export function colourAt(
  palette: readonly string[],
  domain: [number, number],
  value: number
): string {
  if (!Number.isFinite(value)) return 'transparent';
  const [lo, hi] = domain;
  const t = Math.min(1, Math.max(0, (value - lo) / (hi - lo)));
  const pos = t * (palette.length - 1);
  const k = Math.min(palette.length - 2, Math.floor(pos));
  const f = pos - k;
  const a = hexToRgb(palette[k]!);
  const b = hexToRgb(palette[k + 1]!);
  const mix = a.map((x, j) => Math.round(x + (b[j]! - x) * f));
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
}

/** CSS linear-gradient for a legend bar. */
export function gradient(palette: readonly string[]): string {
  const n = palette.length;
  return `linear-gradient(to right, ${palette.map((c, k) => `${c} ${((100 * k) / (n - 1)).toFixed(1)}%`).join(', ')})`;
}
