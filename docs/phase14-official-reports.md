# Phase 14 — Official technical reports and evidence recovery

Baseline: Phase13 `386b8fdeb6192913c3aaf8b7a2bf9ce229d5b75f`, Draft PR#3. Independent branch `feat/phase14-official-reports`, stacked on Phase13; no earlier PR was merged. Study run `20261104T045200-525bf851`, research cutoff2026-11-03, acquisition through2026-11-04; formal cutoff2026-10-29 remains unchanged.

## Measured research increment

| Item | Phase13 | Phase14 |
|---|---:|---:|
| Canonical registry groups |31|31|
| Resource-defined analysis cases |21|21|
| Selected validated numeric statements |315|321|
| Selected source snapshots (not documents) |204|242|
| PDF snapshot entries / distinct PDF SHA |54 /52|58 /56|
| Recognized documents |27|32|
| Validated document observations, including NULL text |528|566|
| Scorable R / S / T / D / I / C |21 /10 /0 /9 /19 /8|21 /10 /0 /9 /19 /8|
| Formal C1 / full evidence / strict development |0 /0 /0|0 /0 /0|
| Unresolved deposit pairs / government candidate relations |36 /112|36 /112|

The six added numeric statements are automatically recovered **existing Salazar p7 cells**:230Mt,1178ppm TREO, Pr6O11=55ppm, Nd2O3=193ppm, Dy2O3=22ppm and Tb4O7=4.0ppm. They corroborate existing scoped knowledge; they are not six new measurements, new Projects or new scoring criteria. Original tokens, oxide definitions including Y2O3, units, table bbox, source SHA and physical page are retained. No numeric observation was removed. Raw AUTO_VALIDATED database domain counts use a different grouping from selected statement counts; the unchanged `compare_runs` definition supplies315→321.

Four new WAMEX originals were actually downloaded through the public report interface:

| Report / file native ID | Pages | Role | SHA-256 |
|---|---:|---|---|
|A104804 /423301|2|Yangibana lithological logging codes; appendix|fe89b4e4c4ebc1baa493f5d9dfcaef6bc4ce3645b1d8cf09d82f9a5bceb1ecb9|
|A107882 /440687|46|Mt Weld2014–2015 annual technical report|6faf69a2970df7948b3d04ddb5835eec18302d4d6e2896e8013fb45de24b0dfa|
|A118927 /534767|22|Yangibana2017–2018 annual technical report|0ee87a6876f4ab20b39d67303f84f0cdf04372a4588c6cb9a74a741b33481736|
|A118927 /535165|34|Yangibana magnetic modelling; appendix|56471f58306f36b3fc8f58488bd89961a4275a2c612c196a63eaf506d77f8cb8|

All104 physical pages yielded native text. The two complete annual reports generated52 candidates; the two appendices generated no eligible numerical candidates. Their source dates describe **open-file release**, not resource effectiveness or completion of a new current engineering study. New official documents added no validated numeric performance value in this release. The38 added validated document observations comprise6 numeric cells,31 Technical descriptive disclosures and1 Development descriptive disclosure. The Salazar original had not previously entered the selected full-document pipeline, explaining32 recognized documents rather than31.

Technical inventory changes274→305 DESCRIPTIVE_ONLY,573→576 NOT_COMPARABLE, and4→4 NUMERIC_COMPARABLE rows. Those four rows still represent two independent DFS Projects. Main T1 remains0. For example, the historical Mt Weld report p31 discloses69% recovery at30% REO concentrate grade for stockpile test pits; automatic attribution/context and common endpoint/scale conditions are not established. This is retained as a candidate, not substituted for current overall recovery.

## Official discovery and live outcomes

[WAMEX official report index](https://public-services.slip.wa.gov.au/public/rest/services/SLIP_Public_Services/Industry_and_Mining/MapServer/22) supplies native A-number, title, author/company/operator, dates, keywords, abstract, commodity, permanent details and report polygons. Existing inventory-checked ArcGIS retrieval is reused. The final bounded query, report year≥2015 and six registered WA name contexts, matched42 and fetched30 records;12 are deliberately outside the budget. It is not an exhaustive WA census. Earlier bounded work retained30 other A-numbers. Across locked execution receipts there are60 distinct WAMEX report IDs and16 GSQ report IDs, **not76 Projects**. Candidate name/company relations are retained; no new confirmed cross-source Project relation, physical entity or resource rollup is claimed.

The public WAMEX UI uses a read-only POST to `ReportDocuments_Read`. This was confirmed by actual public-page transport and a live response. The bounded reader checks report IDs, list count and file identities; it uses up to four detail lists and two document attempts. Large/unknown-size files and logging-code appendices stay explicitly deferred. Published receipts omit transient signed download URLs entirely. Ignored originals are privately hash-bound; manifests use permanent report pages, native file IDs, original filenames, edition fingerprints and actual downloaded SHA. Retry/byte budgets and SHA verification reuse the existing request/snapshot code. Stable identity plus unchanged file edition reuses bytes; an edition change triggers reacquisition while preserving earlier snapshots, even if content ultimately has the same SHA.

[GSQ's official API guide](https://github.com/geological-survey-of-queensland/open-data-api) and published downloader were inspected. Actual `package_search` and `package_show` calls succeed. Two simple bounded queries returned8/302 and8/381 records, two pages each. HTTP200 `success=false`, duplicate IDs, count drift and premature empty pages are rejected. A failed package detail does not discard valid search records or other sources. Metadata includes package/resource IDs, open-file dates, report types, commodity, geometry/extent where supplied, and resource URLs. Historical reports are not current JORC statements; no QLD Project is promoted from a report name.

The final prioritized live run had7 successful metadata/search operations,0 metadata failures,2 new PDFs and5 non-PDF download responses: **2/7 document attempts**, parser artifacts2/2. The same configuration rerun reused the two originals and their extraction artifacts, downloaded0 new originals and again recorded5 non-PDF failures. Five original S3 attempts earlier returned403; complex search queries also encountered403, whereas documented simple queries worked. No account login, terms submission, guessed protected URL, CAPTCHA bypass or paid API was used. Results across changed exploratory configurations are not pooled into a single success rate. The earlier bounded run acquired the other two originals listed above.

The existing workflow now has separate scientific replay and live-update jobs. Live acquisition parses originals through the current acquisition day, independently of the frozen study cutoff. A regression test confirms that a newer public original can be parsed while remaining outside the historical research selection and without opening a second database. A partial live result exits nonzero and publishes explicit status/artifacts, without invalidating frozen science. A local execution of the exact summary step verified nonzero status and valid JSON for the real PARTIAL_FAILURE receipt. Successful public snapshot archival is retained behind the separate live outcome and publication scan. A green offline job does not claim a successful live update; scientific yield is NULL until Evidence Selection/database rebuild, not set to zero by transport status.

[DIGS](https://www.resources.nsw.gov.au/geological-survey/digs), [GEMIS](https://geoscience.nt.gov.au/gemis/ntgsjspui/help/index.html), [SARIG catalogue](https://www.energymining.sa.gov.au/industry/geological-survey/products-and-services/map-viewers-databases-and-services/sarig-catalogue) and [TIGER](https://www.mrt.tas.gov.au/products/database_searches) public search/download documentation was assessed. Full report API, pagination and access contracts were not established in this bounded phase, so no speculative adapters were added. EPBC was not integrated.

## PDF validation and scientific scope

Parser v4 extends the existing positioned-column reader to explicit native total rows, vertically split category/header cells, post-table captions and printed oxide headers. It does not infer values, move values across tables or repair unreadable decimal points. Parser v1–3 and frozen policies remain supported. Development and untuned documents are separate:

| Test set | Phase13 parser TP/FP/FN | Phase14 parser TP/FP/FN |
|---|---|---|
|Fixed22-cell development set|13 /0 /9|13 /0 /9|
|Salazar six cells, now explicitly development|0 /0 /6|6 /0 /0|
|Untuned North Stanmore PFS, four cells|0 /0 /4|0 /0 /4|

Untuned Goschen THM/Ore Reserve control is one true negative in both versions. North Stanmore/Goschen were not used to adjust parser rules; they were available in the corpus, so this is **not blind or independent human validation**. Scope and missing on-page basis still prevent those four admissions. No demonstrated cross-document recall improvement or national accuracy is claimed. Frozen Phase13 Salazar/Burracoppin results and Wudinna moisture/Mt Weld tailings/Cummins phosphate controls remain reproducible.

North Stanmore PFS pp8/35 explicitly contrasts the2025 and2026 MRE, heritage-related Mafeking Bora exclusion, revised footprint, additional drilling/classification, and300ppm TREO cutoff excluding Sc; pp136/144 describe oxide/dry basis. Both estimates remain intact. Existing Selection has no cross-scope supersession rule: a disclosure called updated is not authority to erase the old scope or choose a latest value to restore sample size. Resource-defined therefore remains21. Individual REO image cells previously failed selective OCR; no S1 substitute was introduced.

## Aim A/B/C and reproducibility

All nine existing panels completed with unchanged sizes19/7/8/2/2/10/6/17/2 (see machine-readable panel names). All142 scientific panel CSVs, including rankings, weight/measurement-rounding/cohort/method sensitivity and Monte Carlo results, are byte-exact versus Phase13 after CSV newline normalization. Thus no data/cohort/weight/method ranking change or extra common sample is attributed to this phase. Aim C gains source-bound descriptive disclosures; mineral mentions are not asserted primary host minerals, and no causal or underpowered multivariate claim is made.

Production database remains `work/phase5/canonical.sqlite`. All7,555 existing IDs remain, no new ID, Schema/table or dependency was added, and integrity/foreign keys pass. No formal gates, processing complexity, recovery definition, AHP weights, scores or R engine changed. The code content SHA is `82315d87d1030a57a2e936e84bada701cf10b2b2a1cd1d86ea109d216f5dd9bb`; the frozen run records development-time parent386b8fd, not the implementation commit.

Local verification:199 Python tests passed in295.195s; all three R invariant families passed. Phase13 replay preserves142 panel CSVs plus7 evidence exports. Phase14 canonical-to-clean comparison preserves the same142+7 exactly. Two independent clean runs and GitHub Actions are recorded in the final PR/checks and machine-readable summary. There are218 frozen output hashes. Phase5–13 inspection verified1,645 output hashes; six historical Phase5 R.log entries are unpublished local runtime-log exceptions to their old summary hashes, not modified scientific CSVs. Phase6–13 hashes pass. An initial local attempt lacked the R executable path and is retained as FAILED; the successful run uses the existing explicit R path. A test started before a benchmark update observed a version mismatch; the final fixed-version suite passed.

Remaining limits:36 deposit pairs,112 government relation candidates and the Splinter primary-scope gap remain; North Stanmore scope selection is unresolved; GSQ document delivery is not demonstrated; four untuned benchmark cells remain missed; no new measured common Technical endpoint, MCDA sample or formal C1 admission is claimed. Phase14 stops here.

See [structured measured results](../data/phase14_research_summary.json), [live acquisition receipt](../data/phase14_live_acquisition.json), [repeat receipt](../data/phase14_live_idempotence.json), [separate benchmark sets](../data/phase14_document_benchmark.json) and [frozen research](../results/phase14-2026-11-04/README.md).
