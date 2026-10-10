import { describe, expect, it } from 'vitest';
import { DEFAULT_VIEW, parseView, parseWhen, viewToParams, whenToString } from './url';
import { colourAt, stops } from '#lib/map/palettes.ts';
import { num, withUnit } from '#lib/format.ts';

describe('view state in the URL', () => {
  it('round-trips a full view', () => {
    const view = {
      layer: 'trend' as const,
      when: { kind: 'scene' as const, id: 'LC08_L2SP_125059_20180524_02_T1' },
      grid: 'r400',
      zone: 'r400:12:-3',
      camera: { lat: 1.3521, lng: 103.8198, zoom: 11.5 }
    };
    expect(parseView(viewToParams(view))).toEqual(view);
  });

  it('omits defaults and ignores garbage', () => {
    expect(viewToParams(DEFAULT_VIEW).toString()).toBe('');
    const parsed = parseView(
      new URLSearchParams('layer=evil&grid=../x&when=scene:<script>&at=a,b,c')
    );
    expect(parsed).toEqual(DEFAULT_VIEW);
  });

  it('parses every kind of time selection', () => {
    for (const w of [
      'all',
      'season:ne_monsoon',
      'year:2019',
      'scene:LC09_L2SP_125059_20231224_02_T1'
    ]) {
      expect(whenToString(parseWhen(w))).toBe(w);
    }
  });
});

describe('palettes', () => {
  it('spreads stops over the domain and clamps colours', () => {
    const s = stops(['#000000', '#ffffff'], [-2, 2]);
    expect(s).toEqual([
      [-2, '#000000'],
      [2, '#ffffff']
    ]);
    expect(colourAt(['#000000', '#ffffff'], [0, 1], 0.5)).toBe('rgb(128, 128, 128)');
    expect(colourAt(['#000000', '#ffffff'], [0, 1], 9)).toBe('rgb(255, 255, 255)');
    expect(colourAt(['#000000', '#ffffff'], [0, 1], Number.NaN)).toBe('transparent');
  });
});

describe('formatting', () => {
  it('uses a true minus sign and units', () => {
    expect(num(-1.25, 1)).toBe('−1.3');
    expect(num(2, 1, true)).toBe('+2.0');
    expect(num(-0.01, 1)).toBe('0.0');
    expect(withUnit(38.81, '°C')).toBe('38.8 °C');
    expect(withUnit(null, 'K')).toBe('no data');
  });
});
