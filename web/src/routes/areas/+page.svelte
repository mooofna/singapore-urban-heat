<script lang="ts">
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import Plot from '#lib/components/Plot.svelte';
  import { loadAreas, loadManifest } from '#lib/data/load.ts';
  import type { AreaRow, Areas } from '#lib/data/types.ts';
  import { num, pct } from '#lib/format.ts';

  type Level = 'pa' | 'sz';
  type SortKey =
    'alpha' | 'pop_weighted_alpha' | 'hot_spot_share' | 'trend' | 'ndvi' | 'population';

  let areas = $state<Areas | null>(null);
  let error = $state<string | null>(null);
  let level = $state<Level>('pa');
  let sortKey = $state<SortKey>('alpha');
  let descending = $state(true);
  let region = $state('All regions');

  onMount(async () => {
    try {
      await loadManifest();
      areas = await loadAreas();
    } catch (e) {
      error = String(e);
    }
  });

  const columns: { key: SortKey; label: string; title: string }[] = [
    { key: 'alpha', label: 'Relative heat', title: 'Zone effect in kelvin relative to the island' },
    {
      key: 'pop_weighted_alpha',
      label: 'Heat where people live',
      title: 'Relative heat of the 200 m hexagons, weighted by their population'
    },
    {
      key: 'hot_spot_share',
      label: 'Hot spot share',
      title: 'Share of hexagons in significant hot spots'
    },
    { key: 'trend', label: 'Trend', title: 'Theil-Sen trend of relative heat, K per decade' },
    { key: 'ndvi', label: 'NDVI', title: 'Median vegetation index' },
    { key: 'population', label: 'Population', title: 'WorldPop 2023' }
  ];

  const regions = $derived([
    'All regions',
    ...Array.from(new Set((areas?.[level] ?? []).map((a) => a.region))).sort()
  ]);

  const rows = $derived.by(() => {
    const list = (areas?.[level] ?? []).filter(
      (a) => region === 'All regions' || a.region === region
    );
    const val = (a: AreaRow) => a[sortKey] ?? Number.NEGATIVE_INFINITY;
    return [...list].sort((a, b) => (descending ? val(b) - val(a) : val(a) - val(b)));
  });

  const chartRows = $derived(
    rows.filter((r) => r.alpha !== null).slice(0, level === 'pa' ? 55 : 40)
  );

  function sortBy(key: SortKey) {
    if (sortKey === key) descending = !descending;
    else {
      sortKey = key;
      descending = true;
    }
  }

  const mapLink = (a: AreaRow) => `${resolve('/')}?grid=${level}&zone=${encodeURIComponent(a.id)}`;
</script>

<svelte:head>
  <title>Areas | Singapore Urban Heat Explorer</title>
</svelte:head>

<div class="page">
  <h1>Hot and cool neighbourhoods</h1>
  <p class="lead">
    Planning areas and subzones ranked by how much hotter their ground is than the island on the
    same days. "Heat where people live" weights the 200 m hexagons of an area by their population,
    so a hot industrial estate next to a cool park does not dominate.
  </p>

  <div class="controls">
    <div class="seg" role="group" aria-label="Area level">
      <button class="chip" aria-pressed={level === 'pa'} onclick={() => (level = 'pa')}
        >Planning areas</button
      >
      <button class="chip" aria-pressed={level === 'sz'} onclick={() => (level = 'sz')}
        >Subzones</button
      >
    </div>
    <label>
      <span class="visually-hidden">Region</span>
      <select class="chip" bind:value={region}>
        {#each regions as r (r)}<option>{r}</option>{/each}
      </select>
    </label>
  </div>

  {#if error}
    <p class="muted">Could not load the area indicators: {error}</p>
  {:else if !areas}
    <p class="muted">Loading…</p>
  {:else}
    <section class="card chart">
      <h2>
        Relative surface heat, sorted by {columns
          .find((c) => c.key === sortKey)
          ?.label.toLowerCase()}
      </h2>
      <Plot
        label="Bar chart of relative surface heat by area"
        make={(P, width) =>
          P.plot({
            width,
            height: Math.max(240, chartRows.length * 16 + 40),
            marginLeft: 170,
            x: { label: 'Relative heat (K)', grid: true },
            y: { label: null, domain: chartRows.map((r) => r.name) },
            color: { type: 'diverging', scheme: 'rdbu', reverse: true, domain: [-6, 6] },
            marks: [
              P.ruleX([0]),
              P.barX(chartRows, {
                x: 'alpha',
                y: 'name',
                fill: 'alpha',
                tip: true,
                title: (d: AreaRow) => `${d.name}: ${num(d.alpha, 2, true)} K`
              })
            ]
          })}
      />
      {#if level === 'sz' && rows.length > 40}
        <p class="muted small">
          The chart shows the first 40 subzones of the current order; the table lists all.
        </p>
      {/if}
    </section>

    <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable regions must be keyboard focusable, WCAG 2.1.1) -->
    <div class="table-wrap card" tabindex="0" role="region" aria-label="Area table">
      <table>
        <thead>
          <tr>
            <th>{level === 'pa' ? 'Planning area' : 'Subzone'}</th>
            <th>Region</th>
            {#each columns as c (c.key)}
              <th
                class="r"
                title={c.title}
                aria-sort={sortKey === c.key ? (descending ? 'descending' : 'ascending') : 'none'}
              >
                <button class="sort" onclick={() => sortBy(c.key)}
                  >{c.label}{sortKey === c.key ? (descending ? ' ↓' : ' ↑') : ''}</button
                >
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each rows as a (a.id)}
            <tr>
              <td><a href={mapLink(a)}>{a.name}</a></td>
              <td class="muted">{a.region.replace(' Region', '')}</td>
              <td class="r num">{num(a.alpha, 1, true)}</td>
              <td class="r num">{num(a.pop_weighted_alpha, 1, true)}</td>
              <td class="r num">{pct(a.hot_spot_share)}</td>
              <td class="r num">{num(a.trend, 2, true)}</td>
              <td class="r num">{num(a.ndvi, 2)}</td>
              <td class="r num"
                >{a.population === null
                  ? 'no data'
                  : Math.round(a.population).toLocaleString('en-GB')}</td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="muted small">
      Relative heat in kelvin, measured at about 11:16 under clear skies over 2013 to the latest
      scene. Areas without enough clear land observations show no data.
    </p>
  {/if}
</div>

<style>
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    margin: 16px 0;
  }

  .seg {
    display: flex;
    gap: 6px;
  }

  .chart {
    padding: 14px 16px;
    margin-bottom: 20px;
  }

  .chart h2 {
    font-size: 1rem;
    margin: 0 0 8px;
  }

  .table-wrap {
    overflow-x: auto;
  }

  .sort {
    background: none;
    border: none;
    padding: 0;
    font: inherit;
    color: inherit;
    cursor: pointer;
    font-weight: 600;
  }

  td a {
    color: var(--text);
  }

  .small {
    font-size: 0.82rem;
  }
</style>
