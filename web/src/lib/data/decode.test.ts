import { describe, expect, it } from 'vitest';
import { MISSING, chunkOf, decodeInt16, decodeScene, seriesFromChunk } from './decode';

function int16Buffer(values: number[]): ArrayBuffer {
  const buf = new ArrayBuffer(values.length * 2);
  const view = new DataView(buf);
  values.forEach((v, i) => view.setInt16(2 * i, v, true));
  return buf;
}

describe('decodeInt16', () => {
  it('scales hundredths and maps the missing sentinel to NaN', () => {
    const out = decodeInt16(int16Buffer([123, -456, MISSING, 0]));
    expect(out[0]).toBeCloseTo(1.23);
    expect(out[1]).toBeCloseTo(-4.56);
    expect(Number.isNaN(out[2])).toBe(true);
    expect(out[3]).toBe(0);
  });

  it('reads little-endian values at an offset', () => {
    const out = decodeInt16(int16Buffer([1, 2, 3, 4]), 4, 2);
    expect(Array.from(out)).toEqual([0.03, 0.04].map((v) => Math.fround(v)));
  });
});

describe('decodeScene', () => {
  it('splits anomaly and absolute layers', () => {
    const { anomaly, lst } = decodeScene(int16Buffer([100, -100, 3000, MISSING]), 2);
    expect(Array.from(anomaly)).toEqual([1, -1]);
    expect(lst[0]).toBe(30);
    expect(Number.isNaN(lst[1])).toBe(true);
  });

  it('rejects files of the wrong length', () => {
    expect(() => decodeScene(int16Buffer([1, 2, 3]), 2)).toThrow(/expected 8/);
  });
});

describe('chunks', () => {
  it('locates a zone and slices its series', () => {
    expect(chunkOf(1029, 512)).toEqual({ chunk: 2, offset: 5 });
    const chunk = new Float32Array([1, 2, 3, 4, 5, 6]);
    expect(Array.from(seriesFromChunk(chunk, 1, 3))).toEqual([4, 5, 6]);
  });
});
