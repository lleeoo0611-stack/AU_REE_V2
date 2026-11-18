# Index / host review (offline; proposed, not authorization)

Inspected formal config/sources.json, config/discovery.json, acquisition.py and discovery.py. No network requests or acquisition edits. Host classification is endpoint-specific: allowing a document host does not allow crawling its indexes. Runtime redirects are unknown without network inspection; reject undeclared destinations before issuing a request. Existing urllib follows redirects automatically and needs a strict handler.

## Government query APIs: proposed enabled, per-host 3 s and stop on any 4xx
- services.ga.gov.au: seven registered ArcGIS layers, /query inventory and features.
- public-services.slip.wa.gov.au: MINEDEX layer 0 and WAMEX layer 22 ArcGIS /query.
- spatial-gis.information.qld.gov.au: occurrence/status/tenement ArcGIS layers.
- data.stategrowth.tas.gov.au: MRT ArcGIS layer.
- public-gs.geoscience.nsw.gov.au: WFS.
- opendata.maps.vic.gov.au: WFS.
- geology.data.nt.gov.au: WFS.
- services.sarig.sa.gov.au: project WFS.
- wamex.dmp.wa.gov.au: POST /Wamex/Search/ReportDetails/ReportDocuments_Read; government document directory.

## Government directory/search exceptions requiring explicit classification approval
- dasc.dmirs.wa.gov.au: product homepage, Home/GetHierarchy (up to four roots), advertised same-host ZIP. Existing code rejects external download host. This is not a direct-document-only flow.
- geoscience.data.qld.gov.au: CKAN package_search and package_show; government search/index, not just direct download.

## Government direct resources only
- dem-sdp.s3-ap-southeast-2.amazonaws.com: listed SARIG CSV.
- warsydprdstagsdspub.blob.core.windows.net: WAMEX exact returned document URL, subject to approved government lookup exception.
- gsq-prod-ckan-horizon-public.s3.ap-southeast-2.amazonaws.com: GSQ delivery allowlist, subject to approved government lookup exception.
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

## Strict implementation estimate (not implemented)
- acquisition.py: request policy/session reset, redirect guard, per-host stop and HTTP bookkeeping ~70-100 lines; strict refresh/cache branch + declared-SHA committed-fallback validation + report ~110-150 lines.
- cli.py: read evidence_policy.fetch_policy; disable commercial discovery, route allowed government operations, work-cache snapshot selection, report handoff ~35-60 lines.
- Estimated additions/modifications 215-310 lines, plus deletions/replacements counted conservatively under 400. Final git diff is authoritative. No new module/table/schema needed. Existing legacy frozen path must remain unchanged.
- Unknown redirects must not silently expand this list. Government CKAN/DASC exceptions and HTML direct sources should be decided before implementation. Shared-host stop applies across every endpoint and source in one build, not one source at a time.

## Additional migrated direct-document hosts (T1)

company-announcements.afr.com; investorpa.com; newswire.iguana2.com; orbitresources.au; www.itechminerals.com.au; www.marketindex.com.au. Only exact reviewed URLs now in sources.json; no discovery/index/search permission. Any index-like response is not a PDF and must not be followed.
