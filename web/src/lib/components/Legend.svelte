<script lang="ts">
  import { paletteOf, type LayerSpec } from '#lib/map/layers.ts';
  import { gradient } from '#lib/map/palettes.ts';
  import { num } from '#lib/format.ts';

  let { layer }: { layer: LayerSpec } = $props();

  const ticks = $derived.by(() => {
    const [lo, hi] = layer.domain;
    return [lo, (lo + hi) / 2, hi];
  });
  const signed = $derived(layer.palette === 'diverging');
</script>

<div class="legend" aria-label={`Legend for ${layer.label}`}>
  {#if layer.categories}
    <ul>
      {#each layer.categories as c (c.value)}
        <li><span class="swatch" style:background={c.colour}></span>{c.label}</li>
      {/each}
    </ul>
  {:else}
    <div class="bar" style:background={gradient(paletteOf(layer))}></div>
    <div class="ticks num">
      {#each ticks as t, k (k)}
        <span
          >{k === 0 ? '≤ ' : k === 2 ? '≥ ' : ''}{num(
            t,
            Math.abs(t) < 2 && t !== 0 ? 1 : 0,
            signed
          )}</span
        >
      {/each}
    </div>
    {#if layer.unit}<div class="unit muted">{layer.unit}</div>{/if}
  {/if}
</div>

<style>
  .legend {
    font-size: 0.82rem;
  }

  .bar {
    height: 10px;
    border-radius: 3px;
    border: 1px solid var(--border);
  }

  .ticks {
    display: flex;
    justify-content: space-between;
    margin-top: 2px;
  }

  .unit {
    font-size: 0.78rem;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2px 12px;
  }

  li {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .swatch {
    width: 12px;
    height: 12px;
    border-radius: 3px;
    border: 1px solid var(--border);
  }
</style>
