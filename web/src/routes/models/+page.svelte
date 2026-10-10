<script lang="ts">
  import { onMount } from 'svelte';
  import Plot from '#lib/components/Plot.svelte';
  import { loadManifest, loadModel } from '#lib/data/load.ts';
  import type { FittedModel, Manifest, ModelReport } from '#lib/data/types.ts';
  import { num, pValue } from '#lib/format.ts';

  let manifest = $state<Manifest | null>(null);
  let reports = $state<Record<string, ModelReport>>({});
  let grid = $state('r200');
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      manifest = await loadManifest();
      grid = manifest.primary_zone_set;
      const hexSets = manifest.zone_sets.filter((z) => z.kind === 'hex').map((z) => z.name);
      const loaded = await Promise.all(
        hexSets.map((g) => loadModel(g).then((r) => [g, r] as const))
      );
      reports = Object.fromEntries(loaded);
    } catch (e) {
      error = String(e);
    }
  });

  const report = $derived(reports[grid] ?? null);
  const label = $derived(new Map((report?.variables ?? []).map((v) => [v.name, v.label])));
  const byKind = (kind: string) => report?.models.find((m) => m.kind === kind) ?? null;
  const preferred = $derived(report ? byKind(report.lowest_aic) : null);

  interface EffectRow {
    model: string;
    variable: string;
    effect: string;
    estimate: number;
    low: number;
    high: number;
  }

  // Effects comparable across models: OLS and SEM coefficients are marginal effects; for SAR and SDM
  // the direct and total impacts are shown.
  const effects = $derived.by((): EffectRow[] => {
    if (!report) return [];
    const rows: EffectRow[] = [];
    for (const m of report.models) {
      if (m.kind === 'OLS' || m.kind === 'SEM') {
        for (const c of m.coefficients.filter(
          (c) => c.name !== 'constant' && !c.name.startsWith('W ')
        )) {
          rows.push({
            model: m.kind,
            variable: label.get(c.name) ?? c.name,
            effect: 'coefficient',
            estimate: c.estimate,
            low: c.estimate - 1.96 * c.std_error,
            high: c.estimate + 1.96 * c.std_error
          });
        }
      } else {
        for (const i of m.impacts) {
          rows.push({
            model: m.kind,
            variable: label.get(i.name) ?? i.name,
            effect: 'total',
            estimate: i.total,
            low: i.total - 1.96 * i.total_se,
            high: i.total + 1.96 * i.total_se
          });
        }
      }
    }
    return rows;
  });

  const scale = $derived.by(() => {
    const rows: {
      radius: number;
      variable: string;
      estimate: number;
      low: number;
      high: number;
    }[] = [];
    for (const [g, r] of Object.entries(reports)) {
      const sem = r.models.find((m) => m.kind === 'SEM');
      if (!sem) continue;
      for (const c of sem.coefficients.filter((c) => c.name !== 'constant')) {
        rows.push({
          radius: Number(g.slice(1)),
          variable: r.variables.find((v) => v.name === c.name)?.label ?? c.name,
          estimate: c.estimate,
          low: c.estimate - 1.96 * c.std_error,
          high: c.estimate + 1.96 * c.std_error
        });
      }
    }
    return rows;
  });

  const spatial = (m: FittedModel) =>
    m.spatial_parameter
      ? `${m.spatial_parameter.name === 'rho' ? 'ρ' : 'λ'} = ${num(m.spatial_parameter.estimate, 3)}`
      : '';
</script>

<svelte:head>
  <title>Models | Singapore Urban Heat Explorer</title>
</svelte:head>

<div class="page">
  <h1>What explains the heat</h1>
  <p class="lead">
    A spatial regression of each hexagon's relative surface heat on vegetation, water, population
    and HDB public housing. Neighbouring hexagons are alike, so plain least squares overstates
    certainty; spatial lag, spatial error and spatial Durbin models account for that.
  </p>

  {#if error}
    <p class="muted">Could not load the models: {error}</p>
  {:else if !report || !preferred}
    <p class="muted">Loading…</p>
  {:else}
    <div class="controls" role="group" aria-label="Hexagon size">
      {#each Object.keys(reports).sort((a, b) => Number(a.slice(1)) - Number(b.slice(1))) as g (g)}
        <button class="chip" aria-pressed={grid === g} onclick={() => (grid = g)}
          >{g.slice(1)} m hexagons</button
        >
      {/each}
    </div>

    <section class="facts">
      <div class="card fact">
        <span class="muted">Hexagons</span><strong class="num"
          >{report.n.toLocaleString('en-GB')}</strong
        >
      </div>
      <div class="card fact">
        <span class="muted">Period</span><strong class="num"
          >{report.period[0].slice(0, 4)} to {report.period[1].slice(0, 4)}</strong
        >
      </div>
      <div class="card fact">
        <span class="muted">LM tests point to</span><strong
          >{report.lm_decision === 'both' ? 'lag and error' : report.lm_decision}</strong
        >
      </div>
      <div class="card fact">
        <span class="muted">Lowest AIC</span><strong>{report.lowest_aic}</strong>
      </div>
    </section>

    <section class="card block">
      <h2>Effects on relative surface heat</h2>
      <p class="muted small">
        Kelvin per standard deviation of each covariate, with 95% intervals. For the spatial lag and
        Durbin models the bars are total effects (direct plus spillover to neighbours); a raw
        coefficient there is not a marginal effect.
      </p>
      <Plot
        label="Effect estimates with confidence intervals by model"
        make={(P, width) =>
          P.plot({
            width,
            height: 50 + 4 * 15 * report.variables.length,
            marginLeft: 170,
            x: { label: 'K per standard deviation', grid: true },
            y: { axis: null, domain: ['OLS', 'SAR', 'SEM', 'SDM'] },
            fy: {
              label: null,
              axis: 'left',
              domain: report.variables.map((v) => v.label),
              padding: 0.25
            },
            color: {
              legend: true,
              domain: ['OLS', 'SAR', 'SEM', 'SDM'],
              range: ['#8c8a85', '#d6604d', '#2166ac', '#1b7837']
            },
            marks: [
              P.ruleX([0]),
              P.ruleY(effects, {
                fy: 'variable',
                y: 'model',
                x1: 'low',
                x2: 'high',
                stroke: 'model',
                strokeWidth: 2
              }),
              P.dot(effects, {
                fy: 'variable',
                y: 'model',
                x: 'estimate',
                fill: 'model',
                r: 3.5,
                tip: true,
                title: (d: EffectRow) =>
                  `${d.model} ${d.effect}: ${num(d.estimate, 3, true)} K (${num(d.low, 2)} to ${num(d.high, 2)})`
              })
            ]
          })}
      />
    </section>

    <section class="card block">
      <h2>Model comparison</h2>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable regions must be keyboard focusable, WCAG 2.1.1) -->
      <div class="scroll" tabindex="0" role="region" aria-label="Model comparison table">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th class="r">AIC</th>
              <th class="r">Fit</th>
              <th>Fit measure</th>
              <th class="r">Spatial parameter</th>
              <th class="r">Residual Moran's I</th>
            </tr>
          </thead>
          <tbody>
            {#each report.models as m (m.kind)}
              <tr class:best={m.kind === report.lowest_aic}>
                <td>{m.kind}</td>
                <td class="r num">{num(m.aic, 1)}</td>
                <td class="r num">{num(m.fit_measure, 3)}</td>
                <td class="muted">{m.fit_label}</td>
                <td class="r num">{spatial(m)}</td>
                <td class="r num"
                  >{num(m.residual_moran.i, 3)} (p {pValue(m.residual_moran.p_value)})</td
                >
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="muted small">
        A residual Moran's I near zero means the model has absorbed the spatial dependence. The fit
        of SAR and SDM uses the reduced form; the pseudo R² that includes the neighbours' observed
        heat would be higher but is not comparable with OLS.
      </p>
    </section>

    {#if preferred.impacts.length}
      <section class="card block">
        <h2>Direct and spillover effects in the {preferred.kind}</h2>
        <!-- svelte-ignore a11y_no_noninteractive_tabindex (scrollable regions must be keyboard focusable, WCAG 2.1.1) -->
        <div class="scroll" tabindex="0" role="region" aria-label="Effects table">
          <table>
            <thead>
              <tr
                ><th>Covariate</th><th class="r">Direct</th><th class="r">Indirect</th><th class="r"
                  >Total</th
                ></tr
              >
            </thead>
            <tbody>
              {#each preferred.impacts as i (i.name)}
                <tr>
                  <td>{label.get(i.name) ?? i.name}</td>
                  <td class="r num">{num(i.direct, 3, true)} ± {num(1.96 * i.direct_se, 3)}</td>
                  <td class="r num">{num(i.indirect, 3, true)} ± {num(1.96 * i.indirect_se, 3)}</td>
                  <td class="r num">{num(i.total, 3, true)} ± {num(1.96 * i.total_se, 3)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <p class="muted small">
          Direct: change in a hexagon's own heat when its covariate rises by one standard deviation,
          including feedback through neighbours. Indirect: the summed change in all other hexagons.
          Intervals are 95%, from 2,000 Monte Carlo draws.
        </p>
      </section>
    {/if}

    <section class="grid2">
      <div class="card block">
        <h2>Specification tests</h2>
        <table>
          <tbody>
            {#each byKind('OLS')?.lm_tests ?? [] as t (t.name)}
              <tr
                ><td>{t.name}</td><td class="r num">{num(t.statistic, 1)}</td><td class="r num"
                  >p {pValue(t.p_value)}</td
                ></tr
              >
            {/each}
            {#each report.likelihood_ratio_tests as t (t.restricted + t.general)}
              <tr>
                <td>LR {t.restricted} against {t.general}</td>
                <td class="r num">{num(t.statistic, 1)}</td>
                <td class="r num">p {pValue(t.p_value)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="card block">
        <h2>Collinearity</h2>
        <table>
          <tbody>
            {#each report.variables as v (v.name)}
              <tr><td>{v.label}</td><td class="r num">VIF {num(report.vif[v.name], 2)}</td></tr>
            {/each}
          </tbody>
        </table>
        <p class="muted small">Values below 5 indicate no problematic collinearity.</p>
      </div>
    </section>

    {#if scale.length}
      <section class="card block">
        <h2>Does the hexagon size matter?</h2>
        <p class="muted small">
          Spatial error model coefficients across grid sizes, with 95% intervals.
        </p>
        <Plot
          label="Coefficients across hexagon sizes"
          make={(P, width) =>
            P.plot({
              width,
              height: 300,
              x: { label: 'Hexagon circumradius (m)', ticks: [200, 300, 400, 600] },
              y: { label: 'K per standard deviation', grid: true },
              color: { legend: true },
              marks: [
                P.ruleY([0]),
                P.areaY(scale, {
                  x: 'radius',
                  y1: 'low',
                  y2: 'high',
                  fill: 'variable',
                  fillOpacity: 0.12
                }),
                P.line(scale, { x: 'radius', y: 'estimate', stroke: 'variable', marker: 'dot' })
              ]
            })}
        />
      </section>
    {/if}

    <p class="muted small">
      Covariates are standardised; one standard deviation of each, on the {grid.slice(1)} m grid:
      {#each report.variables as v, k (v.name)}{v.label}
        {num(v.sd, v.sd < 1 ? 3 : 2)}{v.unit ? ` ${v.unit}` : ''}{k < report.variables.length - 1
          ? ', '
          : '.'}{/each}
    </p>
  {/if}
</div>

<style>
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 16px 0;
  }

  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }

  .fact {
    padding: 10px 14px;
    display: grid;
    gap: 2px;
  }

  .fact span {
    font-size: 0.8rem;
  }

  .fact strong {
    font-size: 1.25rem;
  }

  .block {
    padding: 14px 16px;
    margin-bottom: 16px;
  }

  .block h2 {
    font-size: 1.02rem;
    margin: 0 0 6px;
  }

  .grid2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 16px;
  }

  .scroll {
    overflow-x: auto;
  }

  tr.best td {
    font-weight: 650;
  }

  .small {
    font-size: 0.82rem;
  }
</style>
