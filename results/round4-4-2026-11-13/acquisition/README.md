# Task 4 catalogue register (written before geometry acquisition)

WA: https://catalogue.data.wa.gov.au/dataset/mining-tenements-dmirs-003
License: CC BY 4.0; evidence dd84aa758a89fccbcec7bf8c87b0d8eca77f07f87ffc31d0ffeb47c5064061d1.
Documented endpoint: https://public-services.slip.wa.gov.au/public/services/SLIP_Public_Services/Industry_and_Mining_WFS/MapServer/WFSServer
Scope: live and pending tenements, NOT historical.

VIC: https://discover.data.vic.gov.au/dataset/mineral-tenements
License: CC BY 4.0; evidence 07ff51ee0d2576871cb68e5c7411153f924c40e94f152292acad20feb2ec11c8.
Documented endpoint: https://opendata.maps.vic.gov.au/geoserver/wfs?request=GetCapabilities&service=WFS
Layer MINTEN. Capability/schema checks precede geometry requests.

TAS: no requests, prior HTTP 403 stop retained.
Raw bytes and request count are recorded in request_log.json. Any failed target is stopped, without alternative routes.

Remaining-state catalogue checks:
- NT: https://data.nt.gov.au/dataset/strike---northern-territory-mineral-titles ; Creative Commons Attribution (official catalogue evidence 781fb18c918dcf050293fb784af10c3faf5e39081c752063cc5a10e689da8e96); documented endpoint https://geoscience.nt.gov.au/contents/prod/Downloads/NT_MineralTitles_shp.zip . The documented ZIP was retrieved after Barkly/Harts own-source IDs were verified. No project-name inference.
- QLD: https://www.data.qld.gov.au/dataset/queensland-mining-and-exploration-tenure-series returned HTTP 202 EMPTY BODY. Catalogue/license could not be validated; conservatively stopped, no alternate route.
- SA: https://location.sa.gov.au/lms/Reports/ReportMetadata.aspx?p_no=949&pa=pirsa returned HTTP 403; stopped, no alternate route.
- NSW: https://www.planningportal.nsw.gov.au/opendata/dataset/nsw-mining-titles returned HTTP 202 EMPTY BODY. Catalogue/license could not be validated; conservatively stopped, no alternate route.
- WA: first GetFeature returned HTTP 400 InvalidParameterValue: sortBy not supported. Despite query-error origin, prompt requires stop after ANY 4xx. No corrected query or alternative endpoint was attempted.


NT follow-up (authorized after task0 gate): official ZIP cf91d27516b4212b7dd795877356827ad042cc90c8fc63d854a74983fed043f2 contains current and historical layers. This pass uses MIN_TITLE_EXPL_GRNT only. Native .prj specifies GDA94 / EPSG:4283, so no datum guessing. All 2090 SHP/SHX/DBF records are aligned and counted; bulk download requires no service pagination. Raw ZIP retains all geometry, co-holders and original field metadata. The earlier lack of own-source IDs was resolved; the configured scope is now the verified 2026 Barkly and Harts ranges.

Largest-tenement fallback correction: all native feature parts sharing a type/numeric title ID are unioned before comparing title areas and calculating the chosen title centroid. Precision still measures the entire project union, not merely that largest title.

NT outcomes: Barkly's complete seven-title union has precision 95,637.13 m, exceeding 25 km, and is not filled. Harts has four of five titles in the current granted layer. EL32406 occurs in the SAME archived package's TITLES_MIN_HISTORICAL.dbf, status Historical/Ceased, DT_CEASED 20230308, UNIQ_ID 18664, holder MICRONISED MINERAL SOLUTIONS PTY LTD. This conflicts with the 2026 schedule used for the row. It is queued as CURRENT_SOURCE_HISTORICAL_TITLE_CONFLICT; no expired/current polygon substitution or source-date inference is made. NT adds zero cells. Final accepted centroid rows remain WIM100 (10,209.25 m) and Nowie (19,639.13 m). Total recorded HTTP requests: 16.
