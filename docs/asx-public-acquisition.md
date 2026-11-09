# ASX public PDF acquisition experiment — 2026-11-09

Branch: `experiment/asx-public-acquisition-20261109`, based on Phase 22 commit
`b5e2a73438e2f3aa9f4adc3ab0f6ff0f898f0fca`. The original checkout stays on
`feat/phase16-technical-model`. No merge or remote publication is part of this experiment.

## Purpose and architecture

Recover accessible ASX originals for the existing source-bound evidence pipeline.
This follows the proposal's ASX/technical-report data collection work and the
project discussion “評估模型取代文件模組”: acquisition precedes extraction and
validation; missing access cannot become zero disclosure, absence, or Project admission.

`asx.fetch_pdf` is an optional adapter inside `discovery.discover`. It returns
original PDF bytes plus a retrieval receipt. Existing immutable snapshots,
manifest appending, source URL identity, SHA checks and cache reuse remain in use.
No second research database, scoring system, extraction policy or admission gate
is introduced. The probe's separate snapshot store is test output only.

ASX legacy `displayAnnouncement.do` may return an HTML wrapper containing an
explicit `pdfURL`. The adapter archives this response, extracts that supplied
public ASX URL, and downloads the corresponding static PDF. It also follows
ASX-host redirects and can try the identical static path on the other ASX host
after a 403, 404 or recognized HTML challenge. It never constructs a PDF path
from an announcement ID. Several different PDF links cause an ambiguity failure.

Each PDF is checked for readable pages. Owner permissions with an empty user
password are supported; a document requiring a password is rejected. Rejected
PDF bytes and received wrappers are retained as source responses. A receipt
preserves the requested URL, actual delivery URL, redirects, original response
hash, stored response hash, PDF hash and physical page count.

The adapter permits HTTPS on the two ASX hosts only, checks every redirect,
uses a one-second interval per requested host, and allows at most three HTTP
steps including redirects and 40 MiB per response. It stops on HTTP 429 or
Retry-After. It sends no terms form, credentials or browser cookies. A challenge
without a verifiable public file URL remains a recorded failure.

## Running the isolated experiment

From this checkout, after installing the existing project dependencies:

```powershell
.venv/Scripts/python.exe tools/probe_asx.py --out work/asx-probe
.venv/Scripts/python.exe -m pytest tests/test_asx.py -q -p no:cacheprovider
```

The default case list is `config/asx_probe_cases.json`. Supply `--cases PATH`
for a JSON object containing 1–4 `{ "key": "…", "url": "…" }` records. Output
must be empty or carry the probe marker. Raw snapshots and manifests remain
under ignored `work/`; `report.json` contains baseline, experimental and repeat
results. Repeat execution checks verified originals before network retrieval.

For an independently prepared research checkout, add `--asx-public` to
`python -m au_ree_v2 discover --root PATH`. The same flag enables the discovery
portion of `acquire`; it does not change targeted `--source-key` refresh.
Programmatic use may set `asx_public_acquisition: true` in the existing discovery
configuration. The normal default remains off. The sparse checkout intentionally
omits the large historical `data/` and `results/` trees; use the probe here.

## Observed live result

The selected cases cover three URLs and **two distinct PDFs**, not three Projects.

| URL case | Previous direct request | Experimental result | Repeat |
|---|---|---|---|
| `displayAnnouncement.do`, ID `03126345` | HTML terms wrapper | Public linked PDF, 167 pages | Verified cache |
| Dubbo scoping 2025, announcements host | PDF bytes | Readable PDF, 69 pages | Verified cache |
| Same Dubbo path, legacy www host | Redirect to PDF | Recorded redirect and same PDF | Verified cache |

The wrapper resolves to `/asxpdf/20260818/pdf/072w8qbl7kfy0n.pdf`, SHA-256
`452dabd702e88c0841c2d029af2127e215e52c2ae9d1144ebe6731f880cde491`.
The Dubbo document SHA-256 is
`734d9ea35fd9617eb2bad21c48fec17cdae08a5c66fa3e3cf7857390d04218ab`, matching
the existing Phase 22 source. All four stored manifest entries passed SHA checks.
The successful run is recorded in `asx-public-acquisition-live.json`; raw files
are retained locally in `work/asx-probe-fixed`.

An initial attempt incorrectly rejected owner-permission PDFs. That failed run
remains in `work/asx-probe`; the corrected behavior has explicit regression tests.
The successful live record predates a final appended-query guard addition; its
source hash identifies the exact code tested, and final automated validation
is recorded separately.

Final validation: **88 distinct test functions and 8 subcases passed** across
the ASX, discovery/eligibility, Phase 13, Phase 14, Phase 21 and Phase 22 suites.
The final code also replays all three captured live routes to the same PDF
hashes without network access. See `asx-public-acquisition-validation.json`.
The full historical suite and full research reconstruction were not run:
available disk space required a sparse checkout and scoped fixture reads.

This establishes recovery of one selected wrapper route and compatibility with
two existing direct routes. It does not establish general CAPTCHA bypass,
archive completeness, history coverage, performance improvement, research usage
licensing, newly validated evidence, C1 approval or any change to MCDA results.
ASX's public [entry page](https://www.asx.com.au/asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId=03126345)
and [company news documentation](https://www.asx.com.au/connectivity-and-data/information-services/company-news)
describe access conditions and the separately offered announcement service.
