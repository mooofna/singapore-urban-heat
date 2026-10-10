import { PALETTES, type PaletteName } from './palettes';
import type { ZoneColumns } from '#lib/data/types.ts';

export type LayerId =
  | 'alpha'
  | 'lst'
  | 'trend'
  | 'lisa'
  | 'ndvi'
  | 'water'
  | 'pop_density'
  | 'hdb_far'
  | 'resid_sem'
  | 'n_obs';

/** Which observations a heat layer summarises. */
export type When =
  | { kind: 'all' }
  | { kind: 'season'; season: string }
  | { kind: 'year'; year: number }
  | { kind: 'scene'; id: string };

export interface Category {
  value: number;
  label: string;
  colour: string;
}

export interface LayerSpec {
  id: LayerId;
  label: string;
  unit: string;
  description: string;
  palette: PaletteName;
  domain: [number, number];
  /** Accepts season, year and scene selections. */
  temporal: 'anomaly' | 'absolute' | false;
  categories?: Category[];
  digits: number;
  group: 'Heat' | 'Urban form' | 'Model';
}

export const LISA_CATEGORIES: Category[] = [
  { value: 1, label: 'Hot spot', colour: '#c51b18' },
  { value: 4, label: 'Hot outlier', colour: '#f4a582' },
  { value: 3, label: 'Cool spot', colour: '#2166ac' },
  { value: 2, label: 'Cool outlier', colour: '#92c5de' },
  { value: 0, label: 'Not significant', colour: '#d9d9d9' }
];

export const LAYERS: LayerSpec[] = [
  {
    id: 'alpha',
    label: 'Relative surface heat',
    unit: 'K',
    description:
      'How much hotter or cooler the ground is than a typical place in Singapore on the same day, at about 11:16 local time under clear skies.',
    palette: 'diverging',
    domain: [-8, 8],
    temporal: 'anomaly',
    digits: 1,
    group: 'Heat'
  },
  {
    id: 'lst',
    label: 'Surface temperature',
    unit: '°C',
    description:
      'Typical land surface temperature on a clear late morning: the island level plus the relative heat of the zone.',
    palette: 'heat',
    domain: [30, 48],
    temporal: 'absolute',
    digits: 1,
    group: 'Heat'
  },
  {
    id: 'trend',
    label: 'Trend of relative heat',
    unit: 'K per decade',
    description:
      'Theil-Sen slope of the relative heat since 2013. Zones without a significant trend (false discovery rate 5%) are faded.',
    palette: 'diverging',
    domain: [-3, 3],
    temporal: false,
    digits: 2,
    group: 'Heat'
  },
  {
    id: 'lisa',
    label: 'Hot and cool spots',
    unit: '',
    description:
      'Local Moran clusters of relative heat with false discovery rate control: hot spots are hot zones among hot neighbours.',
    palette: 'grey',
    domain: [0, 4],
    temporal: false,
    categories: LISA_CATEGORIES,
    digits: 0,
    group: 'Heat'
  },
  {
    id: 'ndvi',
    label: 'Vegetation (NDVI)',
    unit: '',
    description: 'Median NDVI of clear land pixels, from surface reflectance.',
    palette: 'green',
    domain: [0, 0.9],
    temporal: false,
    digits: 2,
    group: 'Urban form'
  },
  {
    id: 'water',
    label: 'Water share',
    unit: '',
    description: 'Median share of clear pixels that Landsat flags as water.',
    palette: 'blue',
    domain: [0, 1],
    temporal: false,
    digits: 2,
    group: 'Urban form'
  },
  {
    id: 'pop_density',
    label: 'Population density',
    unit: 'thousand per km²',
    description: 'WorldPop 2023 constrained population per km² of land.',
    palette: 'purple',
    domain: [0, 60],
    temporal: false,
    digits: 1,
    group: 'Urban form'
  },
  {
    id: 'hdb_far',
    label: 'HDB floor area ratio',
    unit: '',
    description: 'Floor area of HDB public housing (footprint times storeys) per land area.',
    palette: 'orange',
    domain: [0, 4],
    temporal: false,
    digits: 2,
    group: 'Urban form'
  },
  {
    id: 'resid_sem',
    label: 'Unexplained heat',
    unit: 'K',
    description:
      'Residual of the spatial error model: heat that vegetation, water, population and HDB form do not explain.',
    palette: 'diverging',
    domain: [-5, 5],
    temporal: false,
    digits: 1,
    group: 'Model'
  },
  {
    id: 'n_obs',
    label: 'Clear observations',
    unit: 'scenes',
    description: 'Number of scenes in which the zone was clear enough to measure.',
    palette: 'grey',
    domain: [0, 120],
    temporal: false,
    digits: 0,
    group: 'Model'
  }
];

export const layerById = (id: string): LayerSpec =>
  LAYERS.find((l) => l.id === id) ?? (LAYERS[0] as LayerSpec);

export function paletteOf(layer: LayerSpec): readonly string[] {
  return PALETTES[layer.palette];
}

/** Column of a static (or composite) layer; `null` entries are missing. */
export function staticValues(cols: ZoneColumns, layer: LayerSpec, when: When): (number | null)[] {
  if (layer.temporal === 'anomaly' && when.kind === 'season') {
    return cols[`season_${when.season}`] ?? cols.alpha;
  }
  if (layer.temporal === 'anomaly' && when.kind === 'year') {
    return cols[`year_${when.year}`] ?? cols.alpha;
  }
  switch (layer.id) {
    case 'lisa':
      return cols.lisa ?? cols.id.map(() => null);
    case 'resid_sem':
      return cols.resid_sem ?? cols.id.map(() => null);
    case 'n_obs':
      return cols.n_obs;
    default:
      return cols[layer.id];
  }
}

/** Whether a selection is compatible with the layer; incompatible ones fall back to all years. */
export function effectiveWhen(layer: LayerSpec, when: When): When {
  if (!layer.temporal) return { kind: 'all' };
  if (layer.temporal === 'absolute' && (when.kind === 'season' || when.kind === 'year')) {
    return { kind: 'all' };
  }
  return when;
}
