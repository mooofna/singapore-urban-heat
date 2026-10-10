<script lang="ts">
  import { onMount } from 'svelte';
  import Plot from '#lib/components/Plot.svelte';
  import { loadCatalog, loadManifest } from '#lib/data/load.ts';
  import type { CatalogRow, Manifest } from '#lib/data/types.ts';
  import { num, pct, shortDate } from '#lib/format.ts';

  const REPO = 'https://github.com/mooofna/singapore-urban-heat';

  let manifest = $state<Manifest | null>(null);
  let catalog = $state<CatalogRow[]>([]);
  let error = $state<string | null>(null);
  let status = $state<'all' | 'accepted' | 'rejected'>('all');

  onMount(async () => {
    try {
      manifest = await loadManifest();
      catalog = await loadCatalog();
    } catch (e) {
      error = String(e);
    }
  });

  const sources = [
    {
      name: 'Landsat 8 and 9 Collection 2 Level-2',
      provider: 'U.S. Geological Survey, served by the Microsoft Planetary Computer',
      use: 'Surface temperature, surface reflectance, cloud and water masks',
      licence: 'Public domain. Landsat data courtesy of the U.S. Geological Survey.',
      url: 'https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2'
    },
    {
      name: 'HDB Property Information',
      provider: 'Housing and Development Board, data.gov.sg',
      use: 'Storeys, completion year, dwelling units and uses of HDB blocks',
      licence: 'Singapore Open Data Licence version 1.0',
      url: 'https://data.gov.sg/datasets/d_17f5382f26140b1fdae0ba2ef6239d2f/view'
    },
    {
      name: 'HDB Existing Building',
      provider: 'Housing and Development Board, data.gov.sg',
      use: 'Footprints of HDB blocks',
      licence: 'Singapore Open Data Licence version 1.0',
      url: 'https://data.gov.sg/datasets/d_16b157c52ed637edd6ba1232e026258d/view'
    },
    {
      name: 'Master Plan 2019 Planning Area and Subzone Boundaries (No Sea)',
      provider: 'Urban Redevelopment Authority, data.gov.sg',
      use: 'Land polygon, planning areas, subzones',
      licence: 'Singapore Open Data Licence version 1.0',
      url: 'https://data.gov.sg/datasets/d_4765db0e87b9c86336792efe8a1f7a66/view'
    },
    {
      name: 'WorldPop Global 2015 to 2030, release R2025A, constrained, 100 m',
      provider: 'WorldPop, University of Southampton',
      use: 'Population counts',
      licence: 'Creative Commons Attribution 4.0',
      url: 'https://hub.worldpop.org/'
    },
    {
      name: 'Basemap',
      provider: 'OpenFreeMap, OpenMapTiles, OpenStreetMap contributors',
      use: 'Background map in the explorer',
      licence: 'OpenStreetMap data under the Open Database License',
      url: 'https://openfreemap.org/'
    }
  ];

  const shown = $derived(status === 'all' ? catalog : catalog.filter((s) => s.status === status));
  const perYear = $derived.by(() => {
    const out: { year: string; status: string; n: number }[] = [];
    const counts = new Map<string, number>();
    for (const s of catalog) {
      const key = `${s.date.slice(0, 4)}|${s.status === 'accepted' ? 'clear enough' : 'too cloudy'}`;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    for (const [key, n] of counts) {
      const [year, st] = key.split('|');
      out.push({ year: year ?? '', status: st ?? '', n });
    }
    return out;
  });

  const bibtex = $derived(
    `@software{heide_singapore_urban_heat,
  author = {Heide, Maurice},
  title = {Singapore Urban Heat: surface urban heat from every clear Landsat scene},
  url = {${REPO}},
  version = {${manifest?.sgheat_version ?? ''}},
  year = {${(manifest?.generated_at ?? '2026').slice(0, 4)}}
}`
  );
</script>

<svelte:head>
  <title>Data | Singapore Urban Heat Explorer</title>
</svelte:head>

<div class="page">
  <h1>Data and reproducibility</h1>
  <p class="lead">
    Every number on this site comes from open data and a pipeline you can run yourself. A scheduled
    job checks for new Landsat scenes every month, processes them and republishes the site.
  </p>

  {#if manifest}
    <section class="facts">
      <div class="card fact">
        <span class="muted">Data generated</span><strong
          >{shortDate(manifest.generated_at.slice(0, 10))}</strong
        >
      </div>
      <div class="card fact">
        <span class="muted">Pipeline version</span><strong class="num"
          >{manifest.sgheat_version}</strong
        >
      </div>
      <div class="card fact">
        <span class="muted">Code revision</span>
        <strong class="num"
          >{#if manifest.git_sha}<a href={`${REPO}/commit/${manifest.git_sha}`}
              >{manifest.git_sha.slice(0, 7)}</a
            >{:else}unknown{/if}</strong
        >
      </div>
      <div class="card fact">
        <span class="muted">Scenes</span><strong class="num"
          >{manifest.summary.scenes.accepted} of {manifest.summary.scenes.discovered} usable</strong
        >
      </div>
    </section>
  {/if}

  <h2>Sources and licences</h2>
  <div class="sources">
    {#each sources as s (s.name)}
      <article class="card source">
        <h3><a href={s.url}>{s.name}</a></h3>
        <p class="muted">{s.provider}</p>
        <p>{s.use}</p>
        <p class="licence">{s.licence}</p>
      </article>
    {/each}
  </div>
  <p class="muted small">
    Code is released under the MIT licence. Derived data on this site are released under CC BY 4.0,
    with the attributions above. Street names that link the two HDB datasets were resolved with help
    of the OneMap search API (Singapore Land Authority); no OneMap coordinates are redistributed.
  </p>

  <h2>Scene catalog</h2>
  {#if error}
    <p class="muted">Could not load the catalog: {error}</p>
  {:else if catalog.length}
    <section class="card chart">
      <Plot
        label="Scenes per year by usability"
        make={(P, width) =>
          P.plot({
            width,
            height: 220,
            x: { label: null, tickRotate: 0 },
            y: { label: 'Scenes', grid: true },
            color: {
              legend: true,
              domain: ['clear enough', 'too cloudy'],
              range: ['#d6604d', '#bdbdbd']
            },
            marks: [P.barY(perYear, { x: 'year', y: 'n', fill: 'status', tip: true })]
          })}
      />
      <p class="muted small">
        Scenes count as clear enough when at least 30% of Singapore's land is free of clouds and
        shadows. Singapore is often cloudy, so many scenes are partly used: each hexagon keeps only
        the scenes in which it was clear.
      </p>
    </section>

    <div class="controls" role="group" aria-label="Filter scenes">
      {#each ['all', 'accepted', 'rejected'] as st (st)}
        <button
          class="chip"
          aria-pressed={status === st}
          onclick={() => (status = st as typeof status)}>{st}</button
        >
      {/each}
      <span class="muted small">{shown.length} scenes</span>
    </div>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable regions must be keyboard focusable, WCAG 2.1.1) -->
    <div class="card scroll" tabindex="0" role="region" aria-label="Scene catalog table">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Satellite</th>
            <th>Season</th>
            <th class="r">Clear land</th>
            <th class="r">Island level</th>
            <th>Status</th>
            <th>Scene id</th>
          </tr>
        </thead>
        <tbody>
          {#each shown as s (s.id)}
            <tr>
              <td class="num">{s.date}</td>
              <td>{s.platform === 'landsat-9' ? 'Landsat 9' : 'Landsat 8'}</td>
              <td class="muted">{manifest?.seasons[s.season]?.split(' (')[0] ?? s.season}</td>
              <td class="r num">{pct(s.clear)}</td>
              <td class="r num">{s.level === null ? '' : `${num(s.level, 1)} °C`}</td>
              <td>{s.status}</td>
              <td class="mono">{s.id}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <h2>Run it yourself</h2>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable regions must be keyboard focusable, WCAG 2.1.1) -->
  <pre class="card code" tabindex="0"><code
      >git clone {REPO}
cd singapore-urban-heat
uv sync
uv run sgheat run          # downloads, all scenes, analysis, web bundle (about 10 minutes)
cd web && npm ci && npm run dev</code
    ></pre>

  <h2>Cite</h2>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable regions must be keyboard focusable, WCAG 2.1.1) -->
  <pre class="card code" tabindex="0"><code>{bibtex}</code></pre>
</div>

<style>
  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    margin: 16px 0 8px;
  }

  .fact {
    padding: 10px 14px;
    display: grid;
    gap: 2px;
  }

  .fact span {
    font-size: 0.8rem;
  }

  h2 {
    margin-top: 32px;
  }

  .sources {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
  }

  .source {
    padding: 12px 14px;
  }

  .source h3 {
    font-size: 0.98rem;
    margin: 0;
  }

  .source p {
    margin: 4px 0 0;
    font-size: 0.88rem;
  }

  .licence {
    font-size: 0.8rem !important;
  }

  .chart {
    padding: 14px 16px;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin: 14px 0 8px;
  }

  .scroll {
    overflow: auto;
    max-height: 520px;
  }

  .mono,
  .code {
    font-family: var(--mono);
    font-size: 0.82rem;
  }

  .code {
    padding: 12px 14px;
    overflow-x: auto;
    white-space: pre;
  }

  .small {
    font-size: 0.82rem;
  }
</style>
