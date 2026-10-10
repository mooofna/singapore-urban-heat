// Shapes of the files written by `sgheat export` (src/sgheat/export/web.py).

export type ZoneKind = 'hex' | 'area';

export interface ZoneSetMeta {
  name: string;
  kind: ZoneKind;
  n_zones: number;
  years: number[];
  radius_m: number | null;
}

export interface NamedHeat {
  name: string;
  alpha_k: number;
}

export interface Summary {
  scenes: {
    discovered: number;
    accepted: number;
    first: string | null;
    last: string | null;
    landsat8: number;
    landsat9: number;
  };
  zones: { primary: string; n: number; with_composite: number };
  relative_heat: {
    p10_k: number;
    p90_k: number;
    greenest_decile_k: number;
    least_green_decile_k: number;
    hottest_planning_areas: NamedHeat[];
    coolest_planning_areas: NamedHeat[];
  };
  trends: { zones_tested: number; warming_significant: number; cooling_significant: number };
  hdb_join: { match_rate: number; residential_match_rate: number };
  physics?: {
    reference_scene: string;
    single_channel_bias_k: number;
    radiative_transfer_rmse_k: number;
    transmission: number;
  };
  model?: { n: number; lm_decision: string; lowest_aic: string; period: [string, string] };
}

export interface Manifest {
  schema_version: number;
  generated_at: string;
  sgheat_version: string;
  git_sha: string | null;
  git_dirty: boolean;
  data_tag: string;
  primary_zone_set: string;
  zone_sets: ZoneSetMeta[];
  scene_zone_sets: string[];
  series_chunk: number;
  int16_scale: number;
  int16_missing: number;
  seasons: Record<string, string>;
  lisa: Record<string, string>;
  model_period: [string, string];
  summary: Summary;
}

export type SceneStatus = 'pending' | 'accepted' | 'rejected' | 'failed';

export interface CatalogRow {
  id: string;
  date: string;
  time: string;
  platform: 'landsat-8' | 'landsat-9';
  season: string;
  status: SceneStatus;
  reason: string;
  clear: number | null;
  cloud_land: number | null;
  p50: number | null;
  level: number | null;
  n_zones: number;
  series_index: number | null;
}

/** Per-zone columns, every array aligned to the feature index `i` of the zone GeoJSON. */
export interface ZoneColumns {
  id: string[];
  pa: string[];
  name?: string[];
  land_km2: (number | null)[];
  n_obs: number[];
  alpha: (number | null)[];
  lst: (number | null)[];
  trend: (number | null)[];
  trend_q: (number | null)[];
  ndvi: (number | null)[];
  water: (number | null)[];
  pop_density: (number | null)[];
  population: (number | null)[];
  hdb_coverage: (number | null)[];
  hdb_far: (number | null)[];
  hdb_storeys: (number | null)[];
  dist_coast: (number | null)[];
  lisa?: number[];
  resid_sem?: (number | null)[];
  resid_ols?: (number | null)[];
  [season_or_year: `season_${string}` | `year_${number}`]: (number | null)[];
}

export interface Coefficient {
  name: string;
  estimate: number;
  std_error: number;
  statistic: number;
  p_value: number;
  stars: string;
}

export interface Impact {
  name: string;
  direct: number;
  indirect: number;
  total: number;
  direct_se: number;
  indirect_se: number;
  total_se: number;
}

export interface FittedModel {
  kind: 'OLS' | 'SAR' | 'SEM' | 'SDM';
  n: number;
  k: number;
  coefficients: Coefficient[];
  log_likelihood: number;
  aic: number;
  schwarz: number;
  fit_measure: number;
  fit_label: string;
  residual_moran: { i: number; expected: number; z: number; p_value: number };
  spatial_parameter: Coefficient | null;
  impacts: Impact[];
  lm_tests: { name: string; statistic: number; p_value: number }[];
  extra: Record<string, number>;
}

export interface ModelVariable {
  name: string;
  label: string;
  unit: string;
  description: string;
  mean: number;
  sd: number;
}

export interface ModelReport {
  zone_set: string;
  n: number;
  dropped_outside_largest_component: number;
  outcome: {
    name: string;
    label: string;
    unit: string;
    description: string;
    mean: number;
    sd: number;
  };
  variables: ModelVariable[];
  standardised: boolean;
  durbin_exclude: string[];
  vif: Record<string, number>;
  lm_decision: string;
  models: FittedModel[];
  likelihood_ratio_tests: {
    restricted: string;
    general: string;
    statistic: number;
    df: number;
    p_value: number;
  }[];
  lowest_aic: string;
  period: [string, string];
  hdb_completed_by: number;
  worldpop_year: number;
}

export interface AreaRow {
  id: string;
  name: string;
  pa: string;
  region: string;
  alpha: number | null;
  lst: number | null;
  trend: number | null;
  population: number | null;
  pop_weighted_alpha: number | null;
  hot_spot_share: number | null;
  ndvi: number | null;
  hdb_coverage: number | null;
  land_km2: number;
}

export interface Areas {
  pa: AreaRow[];
  sz: AreaRow[];
}

export interface ErrorStats {
  bias_k: number;
  mae_k: number;
  rmse_k: number;
  p95_abs_k: number;
}

export interface PhysicsScene {
  item_id: string;
  platform: string;
  source: string;
  date_sgt: string | null;
  season: string | null;
  n_pixels: number;
  st_mean_c: number;
  brightness: ErrorStats;
  single_channel: ErrorStats;
  radiative_transfer: ErrorStats;
  atmosphere: { transmission_mean: number; upwelled_mean: number };
  sample: { st_c: number[]; single_channel_c: number[]; brightness_c: number[] };
}

export interface PhysicsReport {
  scenes: PhysicsScene[];
  level1_vs_trad: { n_pixels: number; max_abs_diff: number; mean_diff: number } | null;
}
