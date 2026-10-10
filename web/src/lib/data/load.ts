import { resolve } from '$app/paths';
import type { FeatureCollection, Polygon, MultiPolygon } from 'geojson';
import { decodeInt16, decodeScene } from './decode';
import type { Areas, CatalogRow, Manifest, ModelReport, PhysicsReport, ZoneColumns } from './types';

export type ZoneGeometry = FeatureCollection<Polygon | MultiPolygon, { i: number; id: string }>;

const cache = new Map<string, Promise<unknown>>();
let tag = '';

/** Site root including the deployment base path, without a trailing slash. */
function root(): string {
  return resolve('/').replace(/\/$/, '');
}

/** URL of a bundle file, versioned by the data tag so a new data release bypasses caches. */
export function dataUrl(path: string): string {
  const url = `${root()}/data/${path}`;
  return tag ? `${url}?v=${tag}` : url;
}

async function request(path: string): Promise<Response> {
  const res = await fetch(dataUrl(path));
  if (!res.ok) throw new Error(`could not load ${path} (${res.status})`);
  return res;
}

function cached<T>(key: string, load: () => Promise<T>): Promise<T> {
  let hit = cache.get(key) as Promise<T> | undefined;
  if (!hit) {
    hit = load();
    hit.catch(() => cache.delete(key));
    cache.set(key, hit);
  }
  return hit;
}

export function loadManifest(): Promise<Manifest> {
  return cached('manifest', async () => {
    const res = await fetch(`${root()}/data/manifest.json`, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`could not load manifest.json (${res.status})`);
    const manifest = (await res.json()) as Manifest;
    tag = manifest.data_tag;
    return manifest;
  });
}

export const loadJson = <T>(path: string): Promise<T> =>
  cached(path, async () => (await request(path)).json() as Promise<T>);

export const loadCatalog = () => loadJson<CatalogRow[]>('catalog.json');
export const loadAreas = () => loadJson<Areas>('areas.json');
export const loadPhysics = () => loadJson<PhysicsReport>('physics.json');
export const loadModel = (zoneSet: string) => loadJson<ModelReport>(`models/${zoneSet}.json`);
export const loadZoneColumns = (zoneSet: string) => loadJson<ZoneColumns>(`zones/${zoneSet}.json`);
export const loadZoneGeometry = (zoneSet: string) =>
  loadJson<ZoneGeometry>(`zones/${zoneSet}.geo.json`);

export function loadScene(zoneSet: string, itemId: string, nZones: number) {
  return cached(`scene:${zoneSet}:${itemId}`, async () => {
    const buf = await (await request(`scenes/${zoneSet}/${itemId}.bin`)).arrayBuffer();
    return decodeScene(buf, nZones);
  });
}

export function loadSeriesChunk(zoneSet: string, chunk: number) {
  return cached(`series:${zoneSet}:${chunk}`, async () => {
    const buf = await (await request(`series/${zoneSet}/${chunk}.bin`)).arrayBuffer();
    return decodeInt16(buf);
  });
}
