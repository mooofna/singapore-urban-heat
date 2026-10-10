<script lang="ts">
  import { resolve } from '$app/paths';
</script>

<svelte:head>
  <title>About | Singapore Urban Heat Explorer</title>
</svelte:head>

<div class="page prose">
  <h1>About</h1>
  <p class="lead">
    An open, reproducible analysis of where Singapore's ground runs hot, why, and how that pattern
    changes over the years.
  </p>

  <h2>What you are looking at</h2>
  <p>
    Landsat 8 and 9 each pass over Singapore every 16 days, together every 8 days, at about 11:16
    local time. Clouds hide much of Singapore on most of those days, so the pipeline keeps, for
    every hexagon of 0.1 km², only the scenes in which it was clear, and compares it with the rest
    of the island on the same day. The result is a map of relative surface heat built from dozens of
    clear observations per place instead of a single morning, plus a regression of that heat on
    vegetation, water, population and public housing that accounts for the spatial structure of the
    data.
  </p>
  <p>
    Surface temperature is not air temperature. Hot roofs and roads matter for how a district feels,
    but the numbers here describe surfaces, at one time of day, under clear skies. The <a
      href={resolve('/methods')}>methods page</a
    >
    lists every assumption and limitation.
  </p>

  <h2>Origin</h2>
  <p>
    The project began as a course project in data science at Nanyang Technological University in
    Singapore in 2025, which replicated an earlier study (Yong and Lim, 2020) with a single Landsat
    scene from May 2018. This site is a complete rewrite: it uses the atmospherically corrected
    temperature product instead of uncorrected brightness temperature, every clear scene since 2013
    instead of one day, a land and cloud mask, validated building data and spatial regression
    reported with direct and spillover effects. The methods page lists the changes.
  </p>

  <h2>How it stays current</h2>
  <p>
    A scheduled GitHub Actions workflow queries the Planetary Computer catalogue every month. New
    scenes are screened for clouds, processed, and the analysis, the checks and this site are
    rebuilt automatically. Derived data of each update are attached to a release of the repository.
  </p>

  <h2>Author</h2>
  <p>
    Maurice Heide, MSc student in Data Science at ETH Zurich.
    <a href="https://github.com/mooofna">GitHub</a>,
    <a href="https://www.linkedin.com/in/maurice-heide">LinkedIn</a>,
    <a href="https://scholar.google.com/citations?user=x6GTx8kAAAAJ">Google Scholar</a>.
  </p>
  <p>
    Questions, ideas and corrections are welcome as
    <a href="https://github.com/mooofna/singapore-urban-heat/issues">issues</a> or
    <a href="https://github.com/mooofna/singapore-urban-heat/discussions">discussions</a>.
  </p>

  <h2>Acknowledgements</h2>
  <p>
    Built on open data from the U.S. Geological Survey, the Housing and Development Board, the Urban
    Redevelopment Authority and WorldPop, the Microsoft Planetary Computer catalogue, and
    open-source software including PySAL, exactextract, rasterio, GeoPandas, MapLibre, SvelteKit and
    Observable Plot.
  </p>
  <p class="muted small">
    This is an independent research project. It is not affiliated with or endorsed by any Singapore
    government agency or by the data providers.
  </p>
</div>

<style>
  .prose {
    max-width: 72ch;
  }

  .prose p {
    line-height: 1.65;
  }

  h2 {
    margin-top: 28px;
  }

  .small {
    font-size: 0.82rem;
  }
</style>
