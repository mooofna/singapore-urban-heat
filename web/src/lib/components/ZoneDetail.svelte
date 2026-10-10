<script lang="ts">
  import type { CatalogRow, ZoneColumns } from '#lib/data/types.ts';
  import { loadSeriesChunk } from '#lib/data/load.ts';
  import { chunkOf, seriesFromChunk } from '#lib/data/decode.ts';
  import { num, withUnit, pct } from '#lib/format.ts';
  import Plot from './Plot.svelte';

  interface Props {
    index: number;
    cols: ZoneColumns;
    zoneSet: string;
    hasSeries: boolean;
    chunkSize: number;
    scenes: CatalogRow[];
    areaNames: Map<string, string>;
    selectedScene: string | null;
    onclose: () => void;
  }

  let {
    index,
    cols,
    zoneSet,
    hasSeries,
    chunkSize,
    scenes,
    areaNames,
    selectedScene,
    onclose
  }: Props = $props();

  const accepted = $derived(
    scenes
      .filter((s) => s.status === 'accepted' && s.series_index !== null)
      .sort((a, b) => a.series_index! - b.series_index!)
  );
  let series = $state<Float32Array | null>(null);
  let seriesError = $state<string | null>(null);

  $effect(() => {
    series = null;
    seriesError = null;
    if (!hasSeries) return;
    const { chunk, offset } = chunkOf(index, chunkSize);
    const n = accepted.length;
    loadSeriesChunk(zoneSet, chunk)
      .then((c) => (series = seriesFromChunk(c, offset, n)))
      .catch((e) => (seriesError = String(e)));
  });

  const title = $derived(cols.name?.[index] ?? `Hexagon ${cols.id[index]}`);
  const area = $derived(areaNames.get(cols.pa[index] ?? '') ?? null);
  const v = (key: keyof ZoneColumns) =>
    (cols[key] as (number | null)[] | undefined)?.[index] ?? null;
  const significant = $derived((v('trend_q') ?? 1) < 0.05);

  const points = $derived.by(() => {
    if (!series) return [];
    return accepted
      .map((s, k) => ({
        date: new Date(`${s.date}T11:16:00`),
        value: series![k] ?? Number.NaN,
        id: s.id,
        season: s.season
      }))
      .filter((p) => Number.isFinite(p.value));
  });

  const trendLine = $derived.by(() => {
    const slope = v('trend');
    if (slope === null || points.length < 2) return [];
    const perYear = slope / 10;
    const year = (d: Date) => d.getFullYear() + (d.getMonth() + d.getDate() / 31) / 12;
    const resid = points.map((p) => p.value - perYear * year(p.date)).sort((a, b) => a - b);
    const intercept = resid[Math.floor(resid.length / 2)] ?? 0;
    const first = points[0]!.date;
    const last = points.at(-1)!.date;
    return [
      { date: first, value: intercept + perYear * year(first) },
      { date: last, value: intercept + perYear * year(last) }
    ];
  });

  const metrics = $derived([
    { label: 'Relative heat', value: withUnit(v('alpha'), 'K', 1, true) },
    { label: 'Typical surface temperature', value: withUnit(v('lst'), '°C') },
    {
      label: 'Trend',
      value: `${withUnit(v('trend'), 'K per decade', 2, true)}${v('trend') === null ? '' : significant ? '' : ' (not significant)'}`
    },
    { label: 'Clear observations', value: num(v('n_obs'), 0) },
    { label: 'Vegetation (NDVI)', value: num(v('ndvi'), 2) },
    { label: 'Water share', value: pct(v('water')) },
    { label: 'Population density', value: withUnit(v('pop_density'), 'thousand per km²') },
    { label: 'HDB floor area ratio', value: num(v('hdb_far'), 2) },
    { label: 'HDB storeys (mean)', value: num(v('hdb_storeys'), 0) },
    { label: 'Distance to coast', value: withUnit(v('dist_coast'), 'km') }
  ]);
</script>

<aside class="detail card" aria-label="Zone details">
  <header>
    <div>
      <h2>{title}</h2>
      {#if area && !cols.name}<p class="muted">{area}</p>{/if}
    </div>
    <button class="close" onclick={onclose} aria-label="Close details">×</button>
  </header>
  <dl>
    {#each metrics as m (m.label)}
      <div>
        <dt>{m.label}</dt>
        <dd class="num">{m.value}</dd>
      </div>
    {/each}
  </dl>
  {#if hasSeries}
    <h3>Relative heat in every clear scene</h3>
    {#if seriesError}
      <p class="muted">{seriesError}</p>
    {:else if !series}
      <p class="muted">Loading the time series…</p>
    {:else if points.length === 0}
      <p class="muted">This zone was never clear enough to measure.</p>
    {:else}
      <Plot
        label="Relative heat of this zone over time"
        make={(Plot, width) =>
          Plot.plot({
            width,
            height: 200,
            marginLeft: 36,
            marginBottom: 28,
            x: { type: 'time', label: null },
            y: { label: 'K', grid: true, nice: true },
            color: { type: 'diverging', scheme: 'rdbu', reverse: true, domain: [-8, 8] },
            marks: [
              Plot.ruleY([0], { stroke: 'currentColor', strokeOpacity: 0.4 }),
              Plot.dot(points, {
                x: 'date',
                y: 'value',
                fill: 'value',
                r: 3,
                stroke: 'currentColor',
                strokeOpacity: (d: { id: string }) => (d.id === selectedScene ? 1 : 0.25),
                strokeWidth: (d: { id: string }) => (d.id === selectedScene ? 2 : 0.6),
                tip: true,
                title: (d: { date: Date; value: number }) =>
                  `${d.date.toLocaleDateString('en-GB')}: ${num(d.value, 1, true)} K`
              }),
              Plot.line(trendLine, {
                x: 'date',
                y: 'value',
                stroke: 'currentColor',
                strokeDasharray: significant ? undefined : '4,3'
              })
            ]
          })}
      />
      <p class="note muted">
        Each dot is one clear scene: the zone minus the island level of that day. The line is the
        Theil-Sen trend{significant ? '' : ' (dashed: not significant)'}.
      </p>
    {/if}
  {:else}
    <p class="muted note">
      Single scenes and time series are available for the 200 m grid and the planning areas.
    </p>
  {/if}
</aside>

<style>
  .detail {
    padding: 14px 16px;
    max-height: 100%;
    overflow-y: auto;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
  }

  h2 {
    margin: 0;
    font-size: 1.1rem;
  }

  h3 {
    font-size: 0.92rem;
    margin: 14px 0 4px;
  }

  header p {
    margin: 2px 0 0;
  }

  .close {
    border: none;
    background: none;
    font-size: 1.4rem;
    line-height: 1;
    cursor: pointer;
    color: var(--muted);
  }

  dl {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 14px;
    margin: 12px 0 0;
  }

  dt {
    font-size: 0.76rem;
    color: var(--muted);
  }

  dd {
    margin: 0;
    font-weight: 600;
  }

  .note {
    font-size: 0.8rem;
    margin: 4px 0 0;
  }
</style>
