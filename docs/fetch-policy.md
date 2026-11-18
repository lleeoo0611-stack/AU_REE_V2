# Fetch policy: opt-in strict acquisition

Owner approval: 2026-11-13. The only runtime selector is `fetch_policy: strict` in existing `config/evidence_policy.json`. Only `all --refresh` uses this path; all other commands and `rebuild --snapshot-lock` retain historical behavior. This Markdown is documentation, never a program input.

## Binding constraints

- Exact User-Agent: `AU_REE_V2/0.1 public research`.
- Every request, retry and redirect obeys a three-second minimum between requests to the same host. Any 4xx, CAPTCHA or login response stops that host for the whole build. Only timeout and 5xx get at most one retry. No alternate headers, parameters, proxies or browser automation.
- Only exact registered commercial document URLs. No ASX/company index, search or landing traversal. Government APIs and the two directory exceptions below are allowed only within their existing fixed configuration bounds.
- DASC: only configured products, existing GetHierarchy with at most four roots, same-host ZIP only. CKAN: only configured query strings and existing page limits; dynamic candidate query expansion and old resume cursors disabled. WAMEX/GSQ delivery URLs must come exactly from a current approved API response.
- Redirects: HTTPS only, same host or a hardcoded approved host in the same category. Unknown destinations stop before the redirected request; redirects never expand permission. Government API, government resource, ASX, IR/company and aggregator groups are kept separate.
- Newly downloaded bytes go into a fresh per-build directory under `work/`. No prior work cache is a fallback. Strict does not write or modify `data/snapshots` or `data/manifest.json`.
- Fetch failure may use only a committed `data/snapshots` original with bytes matching the declared SHA exactly, labeled `SNAPSHOT_FALLBACK_SAME_SHA`. A successfully fetched but changed SHA is not accepted and does not fall back to old values; all corresponding declarations enter `SOURCE_SHA_CHANGED` review.
- Page markers, identity/deposit declarations and resource scope remain mandatory. A transport success is not scientific acceptance. No stage, OCR confidence or tenement-centroid rule is added here.
- Acquisition CSV has one row per source/official query receipt with raw HTTP evidence. A companion host-group report separates IR/company hosts from third-party aggregators without adding registry schema fields. Aggregator replacement is future work, not an automatic URL change.

## Government query APIs: enabled, per-host 3 s and stop on any 4xx
- services.ga.gov.au: seven registered ArcGIS layers, /query inventory and features.
- public-services.slip.wa.gov.au: MINEDEX layer 0 and WAMEX layer 22 ArcGIS /query.
- spatial-gis.information.qld.gov.au: occurrence/status/tenement ArcGIS layers.
- data.stategrowth.tas.gov.au: MRT ArcGIS layer.
- public-gs.geoscience.nsw.gov.au: WFS.
- opendata.maps.vic.gov.au: WFS.
- geology.data.nt.gov.au: WFS.
- services.sarig.sa.gov.au: project WFS.
- wamex.dmp.wa.gov.au: POST /Wamex/Search/ReportDetails/ReportDocuments_Read; government document directory.

## Approved government directory/search exceptions
- dasc.dmirs.wa.gov.au: product homepage, Home/GetHierarchy (up to four roots), advertised same-host ZIP. Existing code rejects external download host. This is not a direct-document-only flow.
- geoscience.data.qld.gov.au: CKAN package_search and package_show; government search/index, not just direct download.

## Government direct resources only
- dem-sdp.s3-ap-southeast-2.amazonaws.com: listed SARIG CSV.
- warsydprdstagsdspub.blob.core.windows.net: WAMEX exact returned document URL, only exact URLs returned by the approved government lookup.
- gsq-prod-ckan-horizon-public.s3.ap-southeast-2.amazonaws.com: GSQ delivery allowlist, only exact URLs returned by the approved government lookup.
- international.austrade.gov.au: listed prospectus PDF.
- www.industry.gov.au: listed XLSX.
- www.wa.gov.au: listed download PDF.

## Disable index/search/landing traversal
- www.asx.com.au: announcements.do archive template.
- financialfilings.com: companies/year index and filings detail traversal.
- ar3.com.au: announcements and detail traversal.
- asm-au.com: reports/announcements indexes (registered direct PDF remains permitted).
- astronlimited.com.au, www.astronlimited.com.au: investor index (registered direct PDF remains permitted).
- critica.com.au, www.critica.com.au: announcement index/allowlisted variant.
- dreadnoughtresources.com.au: homepage and ?s= search.
- hastingstechmetals.com: announcement index/detail.
- investors.cobraplc.com: announcement index/detail; failed_primary_url is provenance only.
- investors.victorymetalsaustralia.com: announcement index/detail.
- ktaresources.com: project landing traversal.
- lanthanein.com: reports index.
- meekametals.com.au: homepage traversal.
- rarex.com.au: announcement index/detail.
- vhmltd.com.au, www.vhmltd.com.au: project/index traversal.
- www.arultd.com: announcement index (registered direct PDF remains permitted).
- www.marqueeresources.com.au: project landing traversal.
- www.gippslandcriticalminerals.com: project-overview traversal disabled; its exact registered HTML is a separate direct source, not permission to follow links.
- www.ga.gov.au: critical-minerals HTML landing/index, not GA ArcGIS API.
- datadirector.weblink.com.au: commercial API documentation/feasibility probe, disable.

## Commercial direct document hosts only, exact registered URLs
announcements.asx.com.au; api.investi.com.au; assets.birdsoftware.io; assets.ctfassets.net; cdn-api.markitdigital.com; cdn.financialreports.eu; data-api.marketindex.com.au; hermes-cdn.investorhub.com; investornews.com; staff-web.automicgroup.com.au; victorymetalsaustralia.com; wcsecure.weblink.com.au; www.annualreports.com; www.devexresources.com.au; www.iluka.com. Mixed-use asm-au.com / www.arultd.com / www.astronlimited.com.au are noted above. www.londonstockexchange.com has two exact registered HTML articles, no search/index permission.

## Other references, not a current automatic acquisition grant
- raw.githubusercontent.com: two committed-version legacy files, currently managed snapshot inputs, not indexes.
- www.aspecthuntley.com.au: discovery fallback PDF only, not sources registry; do not activate alternate URL after host failure.
- mininghub.com: previous_unavailable_url provenance only; do not fetch.
- d28rz98at9flks.cloudfront.net: GA seed allowed-host only, no listed exact URL. Unknown document target; disable discovery.
- www.planning.vic.gov.au: issuer seed allowed-host only, no listed exact URL. Unknown target; disable discovery.

## Additional migrated direct-document hosts (T1)

company-announcements.afr.com; investorpa.com; newswire.iguana2.com; orbitresources.au; www.itechminerals.com.au; www.marketindex.com.au. Only exact reviewed URLs now in sources.json; no discovery/index/search permission. Any index-like response is not a PDF and must not be followed.
