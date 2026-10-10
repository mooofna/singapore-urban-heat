import type { LayerId, When } from '#lib/map/layers.ts';

export interface ViewState {
  layer: LayerId;
  when: When;
  grid: string;
  zone: string | null;
  camera: { lng: number; lat: number; zoom: number } | null;
}

export const DEFAULT_VIEW: ViewState = {
  layer: 'alpha',
  when: { kind: 'all' },
  grid: 'r200',
  zone: null,
  camera: null
};

const LAYER_IDS: readonly LayerId[] = [
  'alpha',
  'lst',
  'trend',
  'lisa',
  'ndvi',
  'water',
  'pop_density',
  'hdb_far',
  'resid_sem',
  'n_obs'
];

export function whenToString(when: When): string {
  switch (when.kind) {
    case 'all':
      return 'all';
    case 'season':
      return `season:${when.season}`;
    case 'year':
      return `year:${when.year}`;
    case 'scene':
      return `scene:${when.id}`;
    default:
      return 'all';
  }
}

export function parseWhen(text: string | null): When {
  if (!text || text === 'all') return { kind: 'all' };
  const [kind, value] = text.split(':', 2);
  if (kind === 'season' && value) return { kind: 'season', season: value };
  if (kind === 'year' && value && /^\d{4}$/.test(value))
    return { kind: 'year', year: Number(value) };
  if (kind === 'scene' && value && /^L[CO]\d{2}_[A-Z0-9_]+$/.test(value))
    return { kind: 'scene', id: value };
  return { kind: 'all' };
}

export function parseView(params: Pick<URLSearchParams, 'get'>): ViewState {
  const layer = params.get('layer');
  const grid = params.get('grid');
  const zone = params.get('zone');
  const at = params.get('at');
  let camera: ViewState['camera'] = null;
  if (at) {
    const [lat, lng, zoom] = at.split(',').map(Number);
    if ([lat, lng, zoom].every((v) => v !== undefined && Number.isFinite(v))) {
      camera = { lat: lat as number, lng: lng as number, zoom: zoom as number };
    }
  }
  return {
    layer: LAYER_IDS.includes(layer as LayerId) ? (layer as LayerId) : DEFAULT_VIEW.layer,
    when: parseWhen(params.get('when')),
    grid: grid && /^(r\d+|pa|sz)$/.test(grid) ? grid : DEFAULT_VIEW.grid,
    zone: zone && /^[\w:-]{1,40}$/.test(zone) ? zone : null,
    camera
  };
}

export function viewToParams(view: ViewState): URLSearchParams {
  const params = new URLSearchParams();
  if (view.layer !== DEFAULT_VIEW.layer) params.set('layer', view.layer);
  const when = whenToString(view.when);
  if (when !== 'all') params.set('when', when);
  if (view.grid !== DEFAULT_VIEW.grid) params.set('grid', view.grid);
  if (view.zone) params.set('zone', view.zone);
  if (view.camera) {
    const { lat, lng, zoom } = view.camera;
    params.set('at', `${lat.toFixed(4)},${lng.toFixed(4)},${zoom.toFixed(2)}`);
  }
  return params;
}
