// Number formatting for the UI. Negative numbers use the true minus sign.

const MINUS = '−';

export function num(value: number | null | undefined, digits = 1, signed = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'no data';
  const text = Math.abs(value).toLocaleString('en-GB', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
  if (value < 0 && Number(text.replace(/,/g, '')) !== 0) return `${MINUS}${text}`;
  return signed && value > 0 ? `+${text}` : text;
}

export function withUnit(
  value: number | null | undefined,
  unit: string,
  digits = 1,
  signed = false
): string {
  const text = num(value, digits, signed);
  if (text === 'no data' || !unit) return text;
  return unit === '°C' || unit === '%' ? `${text}${unit === '%' ? '%' : ' °C'}` : `${text} ${unit}`;
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'no data';
  return `${num(value * 100, digits)}%`;
}

export function pValue(p: number): string {
  if (!Number.isFinite(p)) return 'n/a';
  if (p < 0.001) return '< 0.001';
  return p.toFixed(3);
}

export function longDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}

export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}
