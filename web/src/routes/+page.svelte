<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { browser } from '$app/env';
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import HexMap from '#lib/map/HexMap.svelte';
  import Legend from '#lib/components/Legend.svelte';
  import Timeline from '#lib/components/Timeline.svelte';
  import ZoneDetail from '#lib/components/ZoneDetail.svelte';
  import {
    loadAreas,
    loadCatalog,
    loadManifest,
    loadScene,
    loadZoneColumns,
    loadZoneGeometry,
    type ZoneGeometry
  } from '#lib/data/load.ts';
  import type { CatalogRow, Manifest, ZoneColumns } from '#lib/data/types.ts';
  import {
    LAYERS,
    effectiveWhen,
    layerById,
    staticValues,
    type LayerId,
    type When
  } from '#lib/map/layers.ts';
  import { DEFAULT_VIEW, parseView, viewToParams, type ViewState } from '#lib/state/url.ts';
  import { longDate, num, withUnit } from '#lib/format.ts';

  let manifest = $state<Manifest | null>(null);
  let catalog = $state<CatalogRow[]>([]);
  let areaNames = $state(new Map<string, string>());
  let outlines = $state<ZoneGeometry | null>(null);
  let geometry = $state<ZoneGeometry | null>(null);
  let cols = $state<ZoneColumns | null>(null);
  let sceneValues = $state<Float32Array | null>(null);
  let error = $state<string | null>(null);

  // URL parameters exist only in the browser; the prerendered page starts from the default view.
  let view = $state<ViewState>(browser ? parseView(page.url.searchParams) : { ...DEFAULT_VIEW });
  let selected = $state<number | null>(null);
  let hover = $state<{ index: number; x: number; y: number } | null>(null);
  let panelOpen = $state(true);

  const layer = $derived(layerById(view.layer));
  const when = $derived(effectiveWhen(layer, view.when));
  const sceneSets = $derived(new Set(manifest?.scene_zone_sets ?? []));
  const gridMeta = $derived(manifest?.zone_sets.find((z) => z.name === view.grid) ?? null);
  const accepted = $derived(catalog.filter((s) => s.status === 'accepted'));
  const years = $derived(gridMeta?.years ?? []);

  onMount(async () => {
    try {
      manifest = await loadManifest();
      if (!manifest.zone_sets.some((z) => z.name === view.grid))
        view.grid = manifest.primary_zone_set;
      const [cat, areas, pa] = await Promise.all([
        loadCatalog(),
        loadAreas(),
        loadZoneGeometry('pa')
      ]);
      catalog = cat;
      areaNames = new Map(areas.pa.map((a) => [a.id, a.name]));
      outlines = pa;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });

  // Zone set (grid) data.
  $effect(() => {
    const grid = view.grid;
    if (!manifest) return;
    let stale = false;
    Promise.all([loadZoneGeometry(grid), loadZoneColumns(grid)])
      .then(([g, c]) => {
        if (stale) return;
        geometry = g;
        cols = c;
        const zone = untrack(() => view.zone);
        const idx = zone ? c.id.indexOf(zone) : -1;
        selected = idx >= 0 ? idx : null;
      })
      .catch((e) => (error = String(e)));
    return () => {
      stale = true;
    };
  });

  // Single-scene values.
  $effect(() => {
    const w = when;
    const grid = view.grid;
    const n = gridMeta?.n_zones ?? 0;
    sceneValues = null;
    if (w.kind !== 'scene' || !sceneSets.has(grid) || n === 0) return;
    let stale = false;
    loadScene(grid, w.id, n)
      .then((s) => {
        if (!stale) sceneValues = layer.temporal === 'absolute' ? s.lst : s.anomaly;
      })
      .catch((e) => (error = String(e)));
    return () => {
      stale = true;
    };
  });

  const values = $derived.by((): ArrayLike<number | null> | null => {
    if (!cols) return null;
    if (when.kind === 'scene') return sceneSets.has(view.grid) ? sceneValues : null;
    return staticValues(cols, layer, when);
  });

  const faded = $derived.by(() => {
    if (!cols || layer.id !== 'trend') return null;
    return cols.trend_q.map((q) => q === null || q >= 0.05);
  });

  // Keep the URL in sync so every view can be shared.
  $effect(() => {
    const params = viewToParams(view).toString();
    const url = `${page.url.pathname}${params ? `?${params}` : ''}`;
    untrack(() => {
      if (url !== `${page.url.pathname}${page.url.search}`) replaceState(url, {});
    });
  });

  function setLayer(id: string) {
    view.layer = id as LayerId;
  }

  function setWhen(w: When) {
    view.when = w;
    if (w.kind === 'scene' && !sceneSets.has(view.grid) && manifest)
      view.grid = manifest.primary_zone_set;
  }

  function select(index: number | null) {
    selected = index;
    // On narrow screens the details replace the controls instead of covering them.
    if (index !== null && window.innerWidth < 1100) panelOpen = false;
    view.zone = index === null || !cols ? null : (cols.id[index] ?? null);
  }

  const gridLabel = (name: string) =>
    name === 'pa' ? 'Planning areas' : name === 'sz' ? 'Subzones' : `Hexagons, ${name.slice(1)} m`;

  const hoverText = $derived.by(() => {
    if (!hover || !cols) return '';
    const name =
      cols.name?.[hover.index] ?? areaNames.get(cols.pa[hover.index] ?? '') ?? cols.id[hover.index];
    const raw = values ? values[hover.index] : null;
    if (layer.categories) {
      const c = layer.categories.find((cat) => cat.value === raw);
      return `${name}: ${c?.label ?? 'no data'}`;
    }
    return `${name}: ${withUnit(raw ?? null, layer.unit, layer.digits, layer.palette === 'diverging')}`;
  });

  const summary = $derived(manifest?.summary ?? null);
</script>

<div class="explorer" class:with-timeline={when.kind === 'scene'}>
  <HexMap
    {geometry}
    {values}
    {faded}
    {layer}
    {selected}
    {outlines}
    camera={view.camera}
    onselect={select}
    onhover={(i, x, y) => (hover = i === null ? null : { index: i, x, y })}
    oncamera={(c) => (view.camera = c)}
  />

  <section class="panel card" class:closed={!panelOpen} aria-label="Map controls">
    <div class="panel-head">
      <h1>Where Singapore's ground runs hot</h1>
      <button
        class="chip collapse"
        onclick={() => (panelOpen = !panelOpen)}
        aria-expanded={panelOpen}>{panelOpen ? 'Hide' : 'Show'}</button
      >
    </div>
    {#if panelOpen}
      {#if summary}
        <p class="intro">
          Surface temperature from <strong>{summary.scenes.accepted}</strong> clear Landsat 8 and 9
          scenes, {summary.scenes.first ? longDate(summary.scenes.first) : ''} to {summary.scenes
            .last
            ? longDate(summary.scenes.last)
            : ''}, averaged over hexagons and compared with the island on the same day.
        </p>
      {/if}

      <label class="field">
        <span>Layer</span>
        <select value={view.layer} onchange={(e) => setLayer(e.currentTarget.value)}>
          {#each ['Heat', 'Urban form', 'Model'] as group (group)}
            <optgroup label={group}>
              {#each LAYERS.filter((l) => l.group === group) as l (l.id)}
                <option value={l.id}>{l.label}</option>
              {/each}
            </optgroup>
          {/each}
        </select>
      </label>
      <p class="desc muted">{layer.description}</p>

      {#if layer.temporal}
        <div class="field" role="group" aria-label="Time selection">
          <span>Observations</span>
          <div class="chips">
            <button
              class="chip"
              aria-pressed={when.kind === 'all'}
              onclick={() => setWhen({ kind: 'all' })}>All years</button
            >
            {#if layer.temporal === 'anomaly'}
              <button
                class="chip"
                aria-pressed={when.kind === 'season'}
                onclick={() => setWhen({ kind: 'season', season: 'sw_monsoon' })}>By season</button
              >
              <button
                class="chip"
                aria-pressed={when.kind === 'year'}
                onclick={() => setWhen({ kind: 'year', year: years.at(-2) ?? 2025 })}
                >By year</button
              >
            {/if}
            <button
              class="chip"
              aria-pressed={when.kind === 'scene'}
              onclick={() => setWhen({ kind: 'scene', id: accepted.at(-1)?.id ?? '' })}
              >Single scene</button
            >
          </div>
        </div>
        {#if when.kind === 'season' && manifest}
          <div class="chips sub">
            {#each Object.entries(manifest.seasons) as [key, label] (key)}
              <button
                class="chip"
                aria-pressed={when.season === key}
                title={label}
                onclick={() => setWhen({ kind: 'season', season: key })}
                >{label.split(' (')[0]}</button
              >
            {/each}
          </div>
        {:else if when.kind === 'year'}
          <label class="field sub">
            <span class="num">{when.year}</span>
            <input
              type="range"
              min={years[0]}
              max={years.at(-1)}
              step="1"
              value={when.year}
              oninput={(e) => setWhen({ kind: 'year', year: Number(e.currentTarget.value) })}
              aria-label="Year"
            />
          </label>
        {/if}
      {/if}

      <label class="field">
        <span>Zones</span>
        <select value={view.grid} onchange={(e) => (view.grid = e.currentTarget.value)}>
          {#each manifest?.zone_sets ?? [] as z (z.name)}
            <option value={z.name} disabled={when.kind === 'scene' && !sceneSets.has(z.name)}
              >{gridLabel(z.name)}</option
            >
          {/each}
        </select>
      </label>

      <Legend {layer} />
      <p class="foot muted">
        Land surface temperature at the 11:16 overpass under clear skies, not air temperature. <a
          href={resolve('/methods')}>How it is computed</a
        >
      </p>
    {/if}
  </section>

  {#if when.kind === 'scene' && catalog.length}
    <div class="timeline-dock card">
      <Timeline
        scenes={catalog}
        selected={when.id}
        onselect={(id) => setWhen({ kind: 'scene', id })}
      />
    </div>
  {/if}

  {#if selected !== null && cols && manifest}
    <div class="detail-dock">
      <ZoneDetail
        index={selected}
        {cols}
        zoneSet={view.grid}
        hasSeries={sceneSets.has(view.grid)}
        chunkSize={manifest.series_chunk}
        scenes={catalog}
        {areaNames}
        selectedScene={when.kind === 'scene' ? when.id : null}
        onclose={() => select(null)}
      />
    </div>
  {/if}

  {#if hover && hoverText}
    <div class="tooltip num" style:left={`${hover.x + 14}px`} style:top={`${hover.y + 14}px`}>
      {hoverText}
    </div>
  {/if}

  {#if error}
    <div class="error card" role="alert">Could not load the data: {error}</div>
  {/if}
</div>

<style>
  .explorer {
    position: relative;
    height: calc(100dvh - 52px);
    overflow: hidden;
  }

  .panel {
    position: absolute;
    top: 12px;
    left: 12px;
    width: min(360px, calc(100% - 24px));
    max-height: calc(100% - 24px);
    overflow-y: auto;
    padding: 14px 16px;
    display: grid;
    gap: 10px;
    z-index: 5;
  }

  .panel-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }

  h1 {
    font-size: 1.15rem;
    margin: 0;
  }

  .intro {
    margin: 0;
    font-size: 0.9rem;
  }

  .field {
    display: grid;
    gap: 4px;
  }

  .field > span {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .field.sub {
    grid-template-columns: auto 1fr;
    align-items: center;
    gap: 10px;
  }

  .field.sub > span {
    color: var(--text);
    font-size: 0.95rem;
    text-transform: none;
  }

  select {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 6px 8px;
  }

  .desc {
    margin: -4px 0 0;
    font-size: 0.82rem;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .chips .chip {
    font-size: 0.82rem;
  }

  .foot {
    font-size: 0.78rem;
    margin: 0;
  }

  .timeline-dock {
    position: absolute;
    left: 384px;
    right: 12px;
    bottom: 28px;
    padding: 8px 12px;
    z-index: 4;
  }

  .detail-dock {
    position: absolute;
    top: 12px;
    right: 56px;
    width: min(380px, calc(100% - 24px));
    max-height: calc(100% - 24px);
    display: flex;
    z-index: 6;
  }

  .tooltip {
    position: absolute;
    pointer-events: none;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 0.8rem;
    box-shadow: var(--shadow);
    z-index: 10;
    white-space: nowrap;
  }

  .error {
    position: absolute;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 14px;
    z-index: 10;
  }

  @media (max-width: 1100px) {
    .timeline-dock {
      left: 12px;
      bottom: 24px;
    }

    .with-timeline .panel {
      max-height: calc(100% - 170px);
    }
  }

  @media (max-width: 720px) {
    .panel {
      top: 8px;
      left: 8px;
      right: 8px;
      width: auto;
      max-height: 55%;
    }

    .panel.closed {
      max-height: none;
    }

    .detail-dock {
      top: auto;
      bottom: 0;
      left: 0;
      right: 0;
      width: auto;
      max-height: 55%;
    }

    .detail-dock :global(.detail) {
      border-radius: 14px 14px 0 0;
      width: 100%;
    }

    .tooltip {
      display: none;
    }
  }
</style>
