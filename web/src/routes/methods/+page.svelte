<script lang="ts">
  import { onMount } from 'svelte';
  import Plot from '#lib/components/Plot.svelte';
  import { loadManifest, loadPhysics } from '#lib/data/load.ts';
  import type { PhysicsReport } from '#lib/data/types.ts';
  import { num, shortDate } from '#lib/format.ts';

  let { data } = $props();
  let physics = $state<PhysicsReport | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      await loadManifest();
      physics = await loadPhysics();
    } catch (e) {
      error = String(e);
    }
  });

  const reference = $derived(physics?.scenes[0] ?? null);
  const scatter = $derived.by(() => {
    if (!reference) return [];
    const s = reference.sample;
    return s.st_c.map((st, k) => ({ st, single: s.single_channel_c[k] ?? Number.NaN }));
  });
  const biasRows = $derived(
    (physics?.scenes ?? []).flatMap((s) => [
      { scene: s, method: 'Brightness temperature', bias: s.brightness.bias_k },
      { scene: s, method: 'Single-channel (course method)', bias: s.single_channel.bias_k },
      { scene: s, method: 'Radiative transfer inversion', bias: s.radiative_transfer.bias_k }
    ])
  );
  type BiasRow = (typeof biasRows)[number];
</script>

<svelte:head>
  <title>Methods | Singapore Urban Heat Explorer</title>
</svelte:head>

<div class="page layout">
  <nav class="toc" aria-label="On this page">
    <strong>On this page</strong>
    <ul>
      {#each data.toc as h (h.id)}
        <li><a href={`#${h.id}`}>{h.text}</a></li>
      {/each}
    </ul>
  </nav>

  <div>
    <section class="card physics" aria-labelledby="physics-title">
      <h2 id="physics-title">Why the atmosphere matters</h2>
      {#if error}
        <p class="muted">The physics report could not be loaded: {error}</p>
      {:else if !physics || !reference}
        <p class="muted">Loading the physics report…</p>
      {:else}
        <p>
          On {shortDate(reference.date_sgt ?? '2018-05-24')} the thermal signal reached the satellite
          with a mean atmospheric transmission of only {num(
            reference.atmosphere.transmission_mean,
            2
          )}. Without an atmospheric correction, the course method placed the ground {num(
            -reference.single_channel.bias_k,
            1
          )} K too cold on average over {reference.n_pixels.toLocaleString('en-GB')} clear land pixels.
          The full inversion with the USGS atmospheric terms is within {num(
            reference.radiative_transfer.rmse_k,
            2
          )} K of the operational product.
        </p>
        <div class="charts">
          <div>
            <h3>Single-channel estimate against USGS surface temperature</h3>
            <Plot
              label="Scatter of single-channel LST against USGS surface temperature"
              make={(P, width) =>
                P.plot({
                  width,
                  height: 260,
                  grid: true,
                  x: { label: 'USGS surface temperature (°C)' },
                  y: { label: 'Single-channel estimate (°C)' },
                  marks: [
                    P.dot(scatter, {
                      x: 'st',
                      y: 'single',
                      r: 1.2,
                      fill: 'currentColor',
                      fillOpacity: 0.25
                    }),
                    P.line(
                      [
                        { a: 25, b: 25 },
                        { a: 60, b: 60 }
                      ],
                      { x: 'a', y: 'b', stroke: '#b2182b', strokeDasharray: '4,3' }
                    ),
                    P.text([{ a: 55, b: 57 }], {
                      x: 'a',
                      y: 'b',
                      text: () => '1:1',
                      fill: '#b2182b'
                    })
                  ]
                })}
            />
          </div>
          <div>
            <h3>Mean error per scene and method</h3>
            <Plot
              label="Mean error of three estimators in each scene against atmospheric transmission"
              make={(P, width) =>
                P.plot({
                  width,
                  height: 260,
                  grid: true,
                  x: { label: 'Atmospheric transmission' },
                  y: { label: 'Mean error (K)' },
                  color: { legend: true, range: ['#8c8a85', '#b2182b', '#2166ac'] },
                  marks: [
                    P.ruleY([0]),
                    P.dot(biasRows, {
                      x: (d: BiasRow) => d.scene.atmosphere.transmission_mean,
                      y: 'bias',
                      fill: 'method',
                      r: 4,
                      tip: true,
                      title: (d: BiasRow) =>
                        `${d.method}, ${d.scene.date_sgt}: ${num(d.bias, 2, true)} K`
                    })
                  ]
                })}
            />
          </div>
        </div>
        {#if physics.level1_vs_trad}
          <p class="muted small">
            Check: the Level-1 band 10 radiance of the reference scene equals the Level-2 thermal
            radiance used here to within {num(physics.level1_vs_trad.max_abs_diff, 4)} W/(m² sr µm).
          </p>
        {/if}
      {/if}
    </section>

    <article class="doc">
      <!-- Rendered at build time from docs/methodology.md, a file in this repository. -->
      {@html data.html}
    </article>
  </div>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr);
    gap: 32px;
    max-width: 1200px;
  }

  .toc {
    position: sticky;
    top: 72px;
    align-self: start;
    font-size: 0.86rem;
  }

  .toc ul {
    list-style: none;
    padding: 0;
    margin: 8px 0 0;
    display: grid;
    gap: 4px;
  }

  .toc a {
    color: var(--muted);
    text-decoration: none;
  }

  .toc a:hover {
    color: var(--text);
  }

  .physics {
    padding: 16px 20px;
    margin-bottom: 24px;
  }

  .physics h2 {
    margin-top: 0;
  }

  .charts {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 20px;
  }

  .charts h3 {
    font-size: 0.9rem;
    margin: 4px 0;
  }

  .small {
    font-size: 0.82rem;
  }

  .doc {
    max-width: 76ch;
    line-height: 1.65;
  }

  .doc :global(h1) {
    font-size: 1.9rem;
  }

  .doc :global(h2) {
    margin-top: 2em;
    scroll-margin-top: 72px;
  }

  .doc :global(.table-wrap) {
    overflow-x: auto;
    margin: 12px 0;
  }

  .doc :global(table) {
    font-size: 0.9rem;
  }

  .doc :global(.katex-display) {
    overflow-x: auto;
    overflow-y: hidden;
    padding: 4px 0;
  }

  .doc :global(code) {
    font-family: var(--mono);
    font-size: 0.9em;
    background: var(--surface-2);
    padding: 1px 4px;
    border-radius: 4px;
  }

  @media (max-width: 900px) {
    .layout {
      grid-template-columns: minmax(0, 1fr);
    }

    .toc {
      position: static;
    }

    .charts {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
