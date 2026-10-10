# Methodology

This page describes every step from satellite pixels to the maps and models in the explorer. Run-specific numbers (scene counts, model estimates) are not written here; they come from the data bundle and are shown next to this text on the website.

## Question and scope

Which features of urban form make the ground in Singapore hotter or cooler than the island as a whole, and where is that pattern changing? The study area is Singapore's land as defined by the URA Master Plan 2019 planning areas (no sea), about 785 km² including the offshore islands.

The quantity analysed is **land surface temperature** (LST): the radiometric temperature of the ground, roofs and tree canopy seen from space. It is not the air temperature people feel, although the two are related. Landsat passes over Singapore at about 11:16 local time, so every result describes a clear late morning.

## Data

| Source | Use | Licence |
| --- | --- | --- |
| Landsat 8 and 9 Collection 2 Level-2, WRS-2 path 125 row 59, via the Microsoft Planetary Computer STAC API | Surface temperature, surface reflectance, cloud mask | Public domain (USGS) |
| HDB Property Information (data.gov.sg) | Block attributes: storeys, completion year, dwelling units, uses | Singapore Open Data Licence v1.0 |
| HDB Existing Building (data.gov.sg) | Block footprints | Singapore Open Data Licence v1.0 |
| URA Master Plan 2019 planning area and subzone boundaries (data.gov.sg) | Land polygon, aggregation units | Singapore Open Data Licence v1.0 |
| WorldPop R2025A constrained population counts, 100 m | Population density | CC BY 4.0 |

Every download is recorded with its checksum, retrieval time and upstream version in a provenance file next to it.

## Surface temperature

The Level-2 surface temperature band `ST_B10` is produced by USGS with a single-channel algorithm that corrects for the atmosphere (with reanalysis profiles) and for surface emissivity (from ASTER GED). Digital numbers convert to kelvin as

$$
T_s = 0.00341802 \cdot \mathrm{DN} + 149.0 .
$$

Clouds, cloud shadows, dilated cloud edges, cirrus and snow are removed with the `QA_PIXEL` bit flags (bits 1 to 5); fill pixels (bit 0) are dropped. Pixels flagged as water (bit 7) are excluded from temperature averages and counted separately as water share.

### Why not compute LST from the thermal band directly?

The textbook route inverts Planck's law for the top-of-atmosphere radiance $L$ of TIRS band 10,

$$
T_b = \frac{K_2}{\ln\left(K_1 / L + 1\right)} ,
$$

and corrects for emissivity $\varepsilon$ with

$$
T = \frac{T_b}{1 + \left(\lambda T_b / \rho\right) \ln \varepsilon}, \qquad \lambda = 10.895\,\mu\mathrm{m}, \quad \rho = h c / k_B = 1.4388 \times 10^{-2}\,\mathrm{m\,K}.
$$

This ignores the atmosphere. Over Singapore's humid air the transmission of the thermal band is low, so the ground looks much colder from space than it is. The package keeps this derivation in `sgheat.physics.lst_educational` and compares three estimators with `ST_B10` on several scenes (Methods page, chart below the text):

1. brightness temperature $T_b$ alone,
2. the single-channel correction with NDVI-threshold emissivity (Sobrino et al. 2004),
3. a full inversion of the radiative transfer equation with the atmospheric terms that USGS publishes alongside `ST_B10`:

$$
L_{\mathrm{TOA}} = \tau \left[ \varepsilon L_s + (1 - \varepsilon) L_{\downarrow} \right] + L_{\uparrow}
\quad\Rightarrow\quad
L_s = \frac{L_{\mathrm{TOA}} - L_{\uparrow} - \tau (1 - \varepsilon) L_{\downarrow}}{\tau \varepsilon} .
$$

The third estimator reproduces the operational product to about a tenth of a kelvin; the first two are biased low by roughly 9 to 17 K depending on humidity. A bias that varies from day to day would also distort any comparison across scenes, which is why the pipeline uses `ST_B10`.

## Spectral indices

Indices are computed on surface reflectance $\rho = 2.75 \times 10^{-5}\,\mathrm{DN} - 0.2$, never on raw digital numbers, because the offset of the scaling changes ratios:

$$
\mathrm{NDVI} = \frac{\rho_{\mathrm{NIR}} - \rho_{\mathrm{red}}}{\rho_{\mathrm{NIR}} + \rho_{\mathrm{red}}}, \qquad
\mathrm{MNDWI} = \frac{\rho_{\mathrm{green}} - \rho_{\mathrm{SWIR1}}}{\rho_{\mathrm{green}} + \rho_{\mathrm{SWIR1}}} .
$$

## Zones

Pixels are aggregated to flat-top hexagons. A hexagon with circumradius $R$ (equal to its edge length) is $2R$ wide between opposite corners, $\sqrt{3}R$ between opposite edges and has area $\tfrac{3\sqrt{3}}{2}R^2$. The primary grid uses $R = 200$ m (about 0.10 km² per hexagon); grids with $R$ = 300, 400 and 600 m test how results depend on scale. Hexagons have stable axial coordinates $(q, r)$ anchored at the origin of UTM zone 48N, so an identifier always refers to the same place. Hexagons with less than half their area on land are dropped, and every zone is clipped to the coastline.

Zonal statistics use an exact coverage matrix $C$ (computed once with exactextract), where $C_{zp}$ is the fraction of pixel $p$ covered by zone $z$. For a layer $v$ and a validity mask $m$ the zone mean is

$$
\bar v_z = \frac{\sum_p C_{zp}\, m_p\, v_p}{\sum_p C_{zp}\, m_p} ,
$$

which is a sparse matrix product per scene. Population is summed the same way on the WorldPop grid, so totals are conserved exactly. The analysis grid is aligned with the Landsat pixel lattice (pixel edges at 15 m modulo 30 m in UTM 48N), so surface temperature is never resampled.

A zone value of a scene is kept when at least 70% of the zone's land is clear and at least 10 pixels of clear land remain. A scene is processed when at least 30% of Singapore's land is clear.

## Separating where from when

Clouds hide different zones on different days, and the island-wide temperature varies with season and weather. Comparing raw averages would mix the two. Instead, the zone by scene matrix $L_{hs}$ (with gaps) is decomposed by Tukey's median polish into

$$
L_{hs} = \mu + \alpha_h + \tau_s + \varepsilon_{hs} ,
$$

where $\alpha_h$ is the **relative surface heat** of zone $h$ and $\tau_s$ the level of scene $s$. Medians make the fit robust to residual cloud edges. The anomaly $a_{hs} = L_{hs} - \mu - \tau_s = \alpha_h + \varepsilon_{hs}$ is what the time series and seasonal or yearly composites show (medians over scenes, at least 5 observations; 3 for single years). The typical surface temperature of a zone is $\mu + \alpha_h$.

Seasons follow the Meteorological Service Singapore: Northeast Monsoon (December to mid-March), inter-monsoon (mid-March to May), Southwest Monsoon (June to September) and inter-monsoon (October and November).

## Trends

For each zone the Theil-Sen slope of $a_{hs}$ against time is reported in kelvin per decade, with a Mann-Kendall test and Benjamini-Hochberg control of the false discovery rate across zones (5%). Because $a_{hs}$ is relative to the island, a positive trend means the zone warms faster than Singapore as a whole, for example where forest gave way to a new town. Zones need at least 20 observations spanning at least 8 years.

## Urban form

The two HDB datasets share no key: property records list block numbers and street names, footprints list block numbers and an internal street code. A bridge from street codes to street names is built from two kinds of evidence: geocoded records that fall inside a footprint with the same block number, and the overlap (Jaccard index) of the block numbers under a code and under a name, accepted only for sets of at least three blocks with a clear margin. The bridge links more than 99% of property records to a footprint without per-block geocoding.

Covariates per zone, all normalised by land area:

* **NDVI**: median over clear scenes of the model period.
* **Water share**: median share of clear pixels flagged as water.
* **Population density**: WorldPop count per km², year matched to the model period.
* **HDB floor area ratio**: footprint area times storeys of HDB blocks per land area.
* **HDB commercial coverage**: footprint area of blocks with shops or a hawker centre per land area.
* **Distance to coast**: from the zone to the outer land boundary.

HDB building coverage (footprint per land area) is computed too but left out of the models because it is collinear with the floor area ratio. Only blocks completed before the model period are counted. Private housing, offices and industry are not in these datasets, which is the main limitation of the covariates.

## Spatial regression

The outcome is $\alpha_h$ estimated from the scenes of the model period. Covariates are standardised, so coefficients are kelvin per standard deviation. Neighbours are hexagons that share an edge (row-standardised weights $W$); the model domain is the largest connected set of zones, which excludes the offshore islands.

1. **OLS** with Lagrange multiplier tests for an omitted spatial lag and for spatially correlated errors, and their robust versions.
2. **Spatial lag model (SAR)**: $y = \rho W y + X\beta + \varepsilon$.
3. **Spatial error model (SEM)**: $y = X\beta + u$, $u = \lambda W u + \varepsilon$.
4. **Spatial Durbin model (SDM)**: $y = \rho W y + X\beta + W X \theta + \varepsilon$, with the lag of distance to coast left out because it would nearly duplicate the variable itself.

All are fitted by maximum likelihood (spreg). In SAR and SDM a coefficient is not a marginal effect: a change at one zone propagates through $S = (I - \rho W)^{-1}$. The reported effects are the averages of LeSage and Pace (2009),

$$
\text{direct} = \tfrac{1}{n}\operatorname{tr}\!\left(S\right)\beta + \tfrac{1}{n}\operatorname{tr}\!\left(S W\right)\theta, \qquad
\text{total} = \frac{\beta + \theta}{1 - \rho}, \qquad
\text{indirect} = \text{total} - \text{direct},
$$

with traces from a power series ($\operatorname{tr} W^j$ estimated with Hutchinson probes) and standard errors from Monte Carlo draws of the parameters.

Reporting rules:

* The fit of SAR and SDM is the squared correlation of $y$ with the reduced-form prediction. The pseudo $R^2$ that includes $\rho W y$ uses the observed outcome of the neighbours and is not comparable with OLS.
* Residual Moran's I uses the filtered residuals for SEM.
* Information criteria are compared only between models fitted to the same observations (enforced in code).
* Hot and cool spots come from local Moran's I with 9,999 permutations and false discovery rate control.

## Validation

* Unit tests check physics against known values and a round trip of the radiative transfer equation, QA bit decoding, hexagon geometry and adjacency against polygon contiguity, mass conservation of zonal sums, recovery of planted effects by the median polish, planted slopes by Theil-Sen, and planted spatial processes by the regression code.
* An offline end-to-end test runs the full pipeline on a 6 km window of a real scene plus synthetic scenes with clouds and a planted warming trend, and checks that the trend is recovered.
* Every run checks invariants (unique identifiers, value ranges, population conservation, residual autocorrelation) before the website is updated.

## Limitations

* Surface temperature at one time of day (about 11:16) under clear skies. Nights, afternoons and cloudy days are not observed, and cloud cover is seasonal.
* Land surface temperature is not air temperature or thermal comfort.
* Thermal pixels are acquired at 100 m and delivered at 30 m; zones of 0.1 km² average a few native thermal pixels.
* Associations, not causes: vegetation, density and building form are intertwined, and NDVI is partly a property of the same surfaces whose temperature is measured.
* HDB covariates cover public housing only; private, commercial and industrial buildings appear only through NDVI and population.
* The HDB footprint layer is a recent snapshot; blocks demolished before it are missing from earlier years.
* Boundaries are from 2019; land reclaimed later is not part of the study area.

## Changes from the course version

The project started as a course project at NTU in 2025 that used one scene (24 May 2018). This rewrite corrects the following: temperature from the atmospherically corrected product instead of uncorrected brightness temperature; a cloud mask; indices on reflectance; a land mask so sea pixels do not enter coastal zones; explicit hexagon size semantics; mass-conserving population sums; validated HDB matching; weights from hexagon contiguity; spatial model fit, residual tests and effects reported as described above; and many scenes instead of one.

## References

* Anselin, L. (1988). *Spatial Econometrics: Methods and Models*. Kluwer.
* Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate. *Journal of the Royal Statistical Society B*, 57(1), 289 to 300.
* Cook, M. et al. (2014). Development of an operational calibration methodology for the Landsat thermal data archive and initial testing of the atmospheric compensation component of a land surface temperature product. *Remote Sensing*, 6(11), 11244 to 11266.
* LeSage, J. and Pace, R. K. (2009). *Introduction to Spatial Econometrics*. CRC Press.
* Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. *Journal of the American Statistical Association*, 63(324), 1379 to 1389.
* Sobrino, J. A., Jimenez-Munoz, J. C. and Paolini, L. (2004). Land surface temperature retrieval from LANDSAT TM 5. *Remote Sensing of Environment*, 90(4), 434 to 440.
* Tukey, J. W. (1977). *Exploratory Data Analysis*. Addison-Wesley.
* Xu, H. (2006). Modification of normalised difference water index (NDWI) to enhance open water features in remotely sensed imagery. *International Journal of Remote Sensing*, 27(14), 3025 to 3033.
* Yong, M. and Lim, K. H. (2020). Urban heat islands: beating the heat with multi-modal spatial analysis. arXiv:2012.03049.
* U.S. Geological Survey (2022). *Landsat 8-9 Collection 2 Level 2 Science Product Guide*.
