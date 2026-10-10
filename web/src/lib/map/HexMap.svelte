<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import type { FeatureCollection } from 'geojson';
  import type { Map as MapLibreMap, ExpressionSpecification, MapMouseEvent } from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import type { ZoneGeometry } from '#lib/data/load.ts';
  import { paletteOf, type LayerSpec } from './layers';
  import { stops } from './palettes';

  interface Camera {
    lng: number;
    lat: number;
    zoom: number;
  }

  interface Props {
    geometry: ZoneGeometry | null;
    values: ArrayLike<number | null> | null;
    faded?: ArrayLike<boolean> | null;
    layer: LayerSpec;
    selected: number | null;
    outlines?: FeatureCollection | null;
    camera?: Camera | null;
    onselect?: (index: number | null) => void;
    onhover?: (index: number | null, x: number, y: number) => void;
    oncamera?: (camera: Camera) => void;
  }

  let {
    geometry,
    values,
    faded = null,
    layer,
    selected,
    outlines = null,
    camera = null,
    onselect,
    onhover,
    oncamera
  }: Props = $props();

  const STYLE = {
    light: 'https://tiles.openfreemap.org/styles/positron',
    dark: 'https://tiles.openfreemap.org/styles/dark'
  };
  const SINGAPORE: [[number, number], [number, number]] = [
    [103.6, 1.205],
    [104.09, 1.475]
  ];
  // Zones without a value (open water, too few clear scenes) stay transparent over the basemap.
  const NO_DATA = 'rgba(0, 0, 0, 0)';

  let container: HTMLDivElement;
  let map: MapLibreMap | null = null;
  let styleReady = $state(false);
  let failed = $state<string | null>(null);
  let hoverId: number | null = null;
  let selectedId: number | null = null;

  function theme(): 'light' | 'dark' {
    const forced = document.documentElement.dataset.theme;
    if (forced === 'light' || forced === 'dark') return forced;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  // Zones go above land cover, buildings, roads and railways but below the labels drawn after them,
  // so place names stay readable on top of the colours.
  function labelLayerAboveBasemap(m: MapLibreMap): string | undefined {
    const layers = m.getStyle().layers ?? [];
    let last = -1;
    layers.forEach((l, k) => {
      if ((l.type === 'line' || l.type === 'fill') && !l.id.startsWith('boundary')) last = k;
    });
    return layers.find((l, k) => k > last && l.type === 'symbol')?.id;
  }

  function fillColour(spec: LayerSpec): ExpressionSpecification {
    if (spec.categories) {
      const pairs = spec.categories.flatMap((c) => [c.value, c.colour]);
      return [
        'match',
        ['feature-state', 'v'],
        ...pairs,
        NO_DATA
      ] as unknown as ExpressionSpecification;
    }
    const flat = stops(paletteOf(spec), spec.domain).flatMap(([v, c]) => [v, c]);
    return [
      'case',
      ['==', ['typeof', ['feature-state', 'v']], 'number'],
      ['interpolate', ['linear'], ['feature-state', 'v'], ...flat],
      NO_DATA
    ] as unknown as ExpressionSpecification;
  }

  function addLayers(m: MapLibreMap) {
    if (!geometry) return;
    const before = labelLayerAboveBasemap(m);
    m.addSource('zones', { type: 'geojson', data: geometry, promoteId: 'i' });
    m.addLayer(
      {
        id: 'zones-fill',
        type: 'fill',
        source: 'zones',
        paint: {
          'fill-color': fillColour(layer),
          'fill-opacity': ['case', ['boolean', ['feature-state', 'f'], false], 0.22, 0.86],
          'fill-outline-color': 'rgba(0,0,0,0)'
        }
      },
      before
    );
    m.addLayer(
      {
        id: 'zones-hover',
        type: 'line',
        source: 'zones',
        paint: {
          'line-color': theme() === 'dark' ? '#ffffff' : '#1d1b18',
          'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 1.2, 0],
          'line-opacity': 0.7
        }
      },
      before
    );
    m.addLayer(
      {
        id: 'zones-selected',
        type: 'line',
        source: 'zones',
        paint: {
          'line-color': theme() === 'dark' ? '#ffffff' : '#1d1b18',
          'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2.6, 0]
        }
      },
      before
    );
    if (outlines) {
      m.addSource('outlines', { type: 'geojson', data: outlines });
      m.addLayer(
        {
          id: 'outlines',
          type: 'line',
          source: 'outlines',
          paint: {
            'line-color': theme() === 'dark' ? '#d0cdc6' : '#4a463f',
            'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.4, 14, 1.2],
            'line-opacity': 0.55
          }
        },
        before
      );
    }
  }

  function applyValues() {
    const m = map;
    if (!m || !styleReady || !geometry || !m.getSource('zones')) return;
    const n = geometry.features.length;
    for (let i = 0; i < n; i++) {
      const raw = values ? values[i] : null;
      const v = raw === null || raw === undefined || Number.isNaN(raw) ? null : raw;
      m.setFeatureState({ source: 'zones', id: i }, { v, f: faded ? Boolean(faded[i]) : false });
    }
  }

  function applySelection() {
    const m = map;
    if (!m || !styleReady || !m.getSource('zones')) return;
    if (selectedId !== null) m.setFeatureState({ source: 'zones', id: selectedId }, { sel: false });
    selectedId = selected;
    if (selected !== null) m.setFeatureState({ source: 'zones', id: selected }, { sel: true });
  }

  function onMove(e: MapMouseEvent & { features?: { id?: string | number }[] }) {
    const m = map;
    if (!m) return;
    const f = e.features?.[0];
    const id = f && f.id !== undefined ? Number(f.id) : null;
    if (id !== hoverId) {
      if (hoverId !== null) m.setFeatureState({ source: 'zones', id: hoverId }, { hover: false });
      hoverId = id;
      if (id !== null) m.setFeatureState({ source: 'zones', id }, { hover: true });
    }
    m.getCanvas().style.cursor = id === null ? '' : 'pointer';
    onhover?.(id, e.point.x, e.point.y);
  }

  function onLeave() {
    if (map && hoverId !== null)
      map.setFeatureState({ source: 'zones', id: hoverId }, { hover: false });
    hoverId = null;
    onhover?.(null, 0, 0);
  }

  let themeListener: (() => void) | null = null;

  onMount(() => {
    let disposed = false;
    (async () => {
      try {
        const [ml, worker] = await Promise.all([
          import('maplibre-gl'),
          import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url')
        ]);
        if (disposed) return;
        ml.setWorkerUrl(worker.default);
        const m = new ml.Map({
          container,
          style: STYLE[theme()],
          bounds: camera ? undefined : SINGAPORE,
          center: camera ? [camera.lng, camera.lat] : undefined,
          zoom: camera?.zoom,
          minZoom: 9,
          maxZoom: 16,
          maxBounds: [
            [103.3, 1.0],
            [104.4, 1.7]
          ],
          attributionControl: { compact: true },
          dragRotate: false,
          pitchWithRotate: false
        });
        m.touchZoomRotate.disableRotation();
        m.addControl(new ml.NavigationControl({ showCompass: false }), 'top-right');
        m.on('style.load', () => {
          addLayers(m);
          styleReady = true;
          applyValues();
          applySelection();
        });
        m.on('mousemove', 'zones-fill', onMove);
        m.on('mouseleave', 'zones-fill', onLeave);
        m.on('click', (e) => {
          const hit = m.queryRenderedFeatures(e.point, { layers: ['zones-fill'] })[0];
          onselect?.(hit && hit.id !== undefined ? Number(hit.id) : null);
        });
        m.on('moveend', () => {
          const c = m.getCenter();
          oncamera?.({ lng: c.lng, lat: c.lat, zoom: m.getZoom() });
        });
        themeListener = () => {
          styleReady = false;
          m.setStyle(STYLE[theme()]);
        };
        window.addEventListener('themechange', themeListener);
        map = m;
      } catch (err) {
        failed = err instanceof Error ? err.message : String(err);
      }
    })();
    return () => {
      disposed = true;
    };
  });

  onDestroy(() => {
    if (themeListener) window.removeEventListener('themechange', themeListener);
    map?.remove();
    map = null;
  });

  // Geometry swap (grid change): rebuild the zone source.
  let shownGeometry: ZoneGeometry | null = null;
  $effect(() => {
    const g = geometry;
    const m = map;
    if (!m || !styleReady || g === shownGeometry) return;
    shownGeometry = g;
    for (const id of ['zones-fill', 'zones-hover', 'zones-selected', 'outlines']) {
      if (m.getLayer(id)) m.removeLayer(id);
    }
    for (const id of ['zones', 'outlines']) if (m.getSource(id)) m.removeSource(id);
    selectedId = null;
    hoverId = null;
    addLayers(m);
    applyValues();
    applySelection();
  });

  $effect(() => {
    const spec = layer;
    if (map && styleReady && map.getLayer('zones-fill')) {
      map.setPaintProperty('zones-fill', 'fill-color', fillColour(spec));
    }
  });

  $effect(() => {
    void values;
    void faded;
    void styleReady;
    applyValues();
  });

  $effect(() => {
    void selected;
    void styleReady;
    applySelection();
  });
</script>

<div
  class="map"
  bind:this={container}
  role="application"
  aria-label="Map of Singapore coloured by the selected layer"
>
  {#if failed}
    <p class="error">The map could not start: {failed}. Your browser needs WebGL2.</p>
  {/if}
</div>

<style>
  .map {
    position: absolute;
    inset: 0;
  }

  .error {
    position: absolute;
    inset: auto 16px 16px;
    padding: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }

  :global(.maplibregl-ctrl-attrib) {
    font-size: 11px;
  }
</style>
