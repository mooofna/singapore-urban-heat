<script lang="ts">
  import '../app.css';
  import 'katex/dist/katex.min.css';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import ThemeToggle from '#lib/components/ThemeToggle.svelte';

  let { children } = $props();

  const links = [
    { href: resolve('/'), route: '/', label: 'Explorer' },
    { href: resolve('/areas'), route: '/areas', label: 'Areas' },
    { href: resolve('/models'), route: '/models', label: 'Models' },
    { href: resolve('/methods'), route: '/methods', label: 'Methods' },
    { href: resolve('/data'), route: '/data', label: 'Data' },
    { href: resolve('/about'), route: '/about', label: 'About' }
  ];

  const current = (route: string) => page.route.id === route;
</script>

<svelte:head>
  <title>Singapore Urban Heat Explorer</title>
  <meta
    name="description"
    content="Surface urban heat in Singapore from every clear Landsat 8 and 9 scene since 2013: maps, trends and spatial regression on urban form."
  />
</svelte:head>

<header>
  <a class="brand" href={resolve('/')} aria-label="Singapore Urban Heat, explorer home">
    <svg viewBox="0 0 64 64" width="22" height="22" aria-hidden="true"
      ><path d="M32 4l24.2 14v28L32 60 7.8 46V18z" fill="#d6604d" /><path
        d="M32 18l12.1 7v14L32 46l-12.1-7V25z"
        fill="#fddbc7"
      /></svg
    >
    <span>Singapore Urban Heat</span>
  </a>
  <nav aria-label="Main">
    {#each links as link (link.href)}
      <a href={link.href} aria-current={current(link.route) ? 'page' : undefined}>{link.label}</a>
    {/each}
  </nav>
  <div class="tools">
    <a
      class="gh"
      href="https://github.com/mooofna/singapore-urban-heat"
      aria-label="Source code on GitHub"
    >
      <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true"
        ><path
          fill="currentColor"
          d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
        /></svg
      >
    </a>
    <ThemeToggle />
  </div>
</header>

<main>
  {@render children()}
</main>

<style>
  header {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 16px;
    height: 52px;
    padding: 0 16px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 650;
    color: var(--text);
    text-decoration: none;
    white-space: nowrap;
  }

  nav {
    display: flex;
    gap: 2px;
    overflow-x: auto;
    scrollbar-width: none;
    flex: 1;
  }

  nav a {
    padding: 6px 10px;
    border-radius: 8px;
    color: var(--muted);
    text-decoration: none;
    white-space: nowrap;
  }

  nav a:hover {
    color: var(--text);
    background: var(--surface-2);
  }

  nav a[aria-current='page'] {
    color: var(--text);
    background: var(--surface-2);
    font-weight: 600;
  }

  .tools {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .gh {
    display: inline-grid;
    place-items: center;
    width: 34px;
    height: 34px;
    color: var(--text);
  }

  main {
    min-height: calc(100dvh - 52px);
  }

  @media (max-width: 720px) {
    .brand span {
      display: none;
    }
    header {
      gap: 8px;
    }
  }
</style>
