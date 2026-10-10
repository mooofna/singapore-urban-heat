<script lang="ts">
  import type { CatalogRow } from '#lib/data/types.ts';
  import { longDate, num, pct } from '#lib/format.ts';

  interface Props {
    scenes: CatalogRow[];
    selected: string | null;
    onselect: (id: string) => void;
  }

  let { scenes, selected, onselect }: Props = $props();

  let width = $state(600);
  const height = 46;
  const pad = 10;

  const accepted = $derived(scenes.filter((s) => s.status === 'accepted'));
  const t0 = $derived(new Date(`${scenes[0]?.date.slice(0, 4) ?? '2013'}-01-01`).getTime());
  const t1 = $derived(
    new Date(`${Number(scenes.at(-1)?.date.slice(0, 4) ?? '2026') + 1}-01-01`).getTime()
  );
  const x = (iso: string) => pad + ((new Date(iso).getTime() - t0) / (t1 - t0)) * (width - 2 * pad);
  const years = $derived.by(() => {
    const out: number[] = [];
    for (let y = new Date(t0).getFullYear(); y <= new Date(t1).getFullYear(); y++) out.push(y);
    return out;
  });
  const current = $derived(accepted.find((s) => s.id === selected) ?? null);

  function step(dir: number) {
    if (!accepted.length) return;
    const k = current ? accepted.indexOf(current) : dir > 0 ? -1 : accepted.length;
    const next = accepted[Math.min(accepted.length - 1, Math.max(0, k + dir))];
    if (next) onselect(next.id);
  }

  function key(e: KeyboardEvent) {
    if (e.key === 'ArrowRight') {
      step(1);
      e.preventDefault();
    } else if (e.key === 'ArrowLeft') {
      step(-1);
      e.preventDefault();
    }
  }
</script>

<div class="timeline">
  <div class="head">
    <button class="chip" onclick={() => step(-1)} aria-label="Previous clear scene">‹</button>
    <div class="label">
      {#if current}
        <strong>{longDate(current.date)}</strong>
        <span class="muted"
          >{current.time} SGT, {current.platform === 'landsat-9' ? 'Landsat 9' : 'Landsat 8'}, {pct(
            current.clear
          )} of land clear, island level {num(current.level, 1)} °C</span
        >
      {:else}
        <span class="muted"
          >Pick a scene: {accepted.length} clear scenes, {scenes.length - accepted.length} too cloudy</span
        >
      {/if}
    </div>
    <button class="chip" onclick={() => step(1)} aria-label="Next clear scene">›</button>
  </div>
  <svg
    bind:clientWidth={width}
    {height}
    role="slider"
    tabindex="0"
    aria-label="Scene timeline"
    aria-valuemin={0}
    aria-valuemax={accepted.length - 1}
    aria-valuenow={current ? accepted.indexOf(current) : 0}
    aria-valuetext={current ? longDate(current.date) : 'none'}
    onkeydown={key}
  >
    {#each years as y (y)}
      <line x1={x(`${y}-01-01`)} x2={x(`${y}-01-01`)} y1="4" y2={height - 14} class="tick" />
      {#if y % 2 === 1 || width > 640}
        <text x={x(`${y}-07-01`)} y={height - 2} class="year">{y}</text>
      {/if}
    {/each}
    {#each scenes as s (s.id)}
      {#if s.status === 'accepted'}
        <circle
          cx={x(s.date)}
          cy="17"
          r={s.id === selected ? 6 : 3.4}
          class:sel={s.id === selected}
          style:opacity={0.35 + 0.65 * (s.clear ?? 0)}
          role="button"
          tabindex="-1"
          aria-label={`Scene of ${longDate(s.date)}`}
          onclick={() => onselect(s.id)}
          onkeydown={(e) => e.key === 'Enter' && onselect(s.id)}
        />
      {:else}
        <circle cx={x(s.date)} cy="30" r="1.6" class="cloudy"
          ><title>{s.date}: too cloudy</title></circle
        >
      {/if}
    {/each}
  </svg>
</div>

<style>
  .timeline {
    display: grid;
    gap: 4px;
  }

  .head {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .label {
    flex: 1;
    display: flex;
    flex-wrap: wrap;
    gap: 0 8px;
    font-size: 0.86rem;
    min-height: 2.6em;
    align-items: center;
  }

  svg {
    width: 100%;
    display: block;
    cursor: pointer;
  }

  .tick {
    stroke: var(--border);
  }

  .year {
    font-size: 10px;
    fill: var(--muted);
    text-anchor: middle;
  }

  circle {
    fill: var(--accent);
  }

  circle.sel {
    fill: var(--text);
    stroke: var(--surface);
    stroke-width: 2;
  }

  .cloudy {
    fill: var(--muted);
    opacity: 0.5;
  }
</style>
