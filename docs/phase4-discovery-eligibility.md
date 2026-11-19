# Source discovery and eligibility compatibility

The existing CLI now includes `au-ree-v2 discover`. Four official/issuer HTML seeds are snapshotted before parsing allowlisted HTTPS PDF links. Content hashes deduplicate documents; failed pages, downloads and PDF parsing are local outcomes. Transient HTTP/network errors retry three times. Static HTML only is supported: this is not a complete ASX feed, recursive crawler or national government service discovery. A page with no allowed PDF links is not proof there are no reports.

A live run discovered and saved ASM Annual Financial Report 2026 (43 physical pages), document SHA-256 `4c1bc8edc6d26b0c5eaf16e385c0e95534c071092624e9d14c338d2783002eb7`. The link title states 25 September 2026, but publication_date remains NULL pending document validation. Some body text has font encoding problems. No numerical observations, funding availability or resource totals were inferred. New pages and PDF snapshots enter the same source manifest and SQLite sources table on the next normal run; discovery creates no Projects or alternate database.

## Gap reconstruction

Every normal analysis rebuilds `unresolved_identity_pairs.csv` (38 pairs, native entity IDs, source hashes, name/state, distance and actual reason), and `primary_scope_gaps.csv` (18 canonical groups, aliases/names, existing unverified resource claims and needed evidence). The 38 are 11 location conflicts and 27 technical-identity evidence gaps. There are no new accepted equivalences in this increment. The 18 indicate absent controlled primary scope in this corpus, not proof of absent public documents.

## C1 compatibility proposal and effect

`config/eligibility_compatibility.json` preserves the inspected prior `C0_F1F2_COHORT_C1C2_V1_20261031` policy verbatim inside the compatibility record. That policy requires ID, ROLE, WINDOW, JORC, PANEL and GIS_RELEASE, signed source evidence, pre-FID active Australian projects, and says the 12/9-criterion panel was not selected. V2 coverage panels do not establish these gates. The earlier PRE_FID_SCOPING_DFS_GATE_V1 coverage policy (70 percent, four domains) also cannot replace the six independent gates.

The compatibility approach keeps V2 panels exploratory and generates versioned per-group/per-gate `NOT_EVALUATED_NO_IMPORTED_GATE_EVIDENCE` records; it does not create another approval procedure, fabricate FAIL/PASS, import obsolete cohort counts, or modify the accepted formal definition. `eligibility_cohorts.csv` separately reports registry, resource-defined, Development, full-evidence and exploratory membership. Formal C1 evaluated/admitted counts are zero **because the gate evidence and fixed panel have not been imported**, not because all Projects failed. A future source-bound import of the correct cutoff-specific ledger and selected panel is needed before formal C1 output. Automatic evidence processing remains independent of formal signature claims.

## Research effect and remaining work

No new scorable resource/recovery/GIS observations were admitted. Resource-defined n=7, strict Development n=0 and full-evidence n=0 remain unchanged. Existing panels (7/5/3/3/2/20) are rerun by the same Python/R pipeline; discovery alone does not change their ranks. Aim A remains partial-panel evaluation, Aim B retains distinct preference/rounding/measurement/cohort treatments, and Aim C remains descriptive. National physical-entity certification, state raw-source acquisition, pagination/ASX feed discovery, reliable PDF extraction, dated finance reaffirmation, and six-domain evidence expansion remain unfinished.

Run `au-ree-v2 discover`, then `au-ree-v2 all --as-of 2026-11-03 --work work/phase4`. Exact analysis replay uses the output snapshot_lock.json; discovery is deliberately a separate explicit network operation and is never executed by offline replay.

## 2026-11 整合 Census 的正式 C1 介面

具來源模式的單一 Census 建置與唯讀匯出會以同一批已選原件、觀測及欄位來源重算三份檔案。歷史 Phase 22 的指定快照仍讀取當時的相容性稽核。原六項 Gate 政策的來源截日是 2026-10-29。2026-11-13 是本次 Census 的來源截日。來源發布、可用時間、觀測生效及取得時間分別記錄。以年／月揭露的日期使用整個區間，跨越政策截日則列待查。

- `formal_c1_gates.csv` 按 Census Project ID 與 Gate 記錄政策差異、定位到的原件、觀測或穩定欄位引文 ID、證據範圍、原文日期、簽核、研究者判定及結果。兩個截日之間的原件不會支持正式 Gate。來自總表名稱、產品、座標或資源的來源只進入初步盤點。PENDING 包括有來源但未獲正式批准的狀況。來源清單受本次已鎖定可用原件範圍限制。
- `formal_c1_panel_comparison.csv` 使用原版 9／12 項事前候選清單；每列列出同名變數、單位與 basis 也相符的觀測，以及缺項，附 Census 分期、州及礦床描述供分層。僅盤點 Census 所有合格日期的已驗證觀測，尚待正式審核的轉換、GIS 發布及編碼另行保留。正式協定的 T1 為處理複雜度；探索性 Technical Disclosure Transparency 的高低不能補足它。未批准的兩套定義都不會建立正式排名。[原版準則選擇協定 §3](https://github.com/lleeoo0611-stack/AU_REE/blob/093d724cc25fc319725bf347fc4d8ab196aadaf3/docs/P0_COHORT_SELECTION_PROTOCOL.md)
- `formal_c1_release.json` 輸出政策與標準版本、原件與決策雜湊、簽核群組、逐項齊全的樣本數、Gate 全過專案、發布 QA 與可發布 ID。正式通過 Gate 後仍須發布 QA。審查通過的 QA 指定精確的決策集合雜湊；若原件或判定改變，舊 QA 不會釋放新版結果。

`eligibility_compatibility.json` 的 imports 保留上游政策、身分 metadata、準則及簽核表的原始位元組與 SHA。實際新增決策時，先以相同的版本化原件機制登錄新檔，保留原版快照。獨立核定的 crosswalk 列需提供 `v2_project_id`、`upstream_review_group_id`、`verified_project_id`、`approval_ref` 與逐格輸出的 `native_id_evidence`。一對多或來源不能定位時保留待審。

`config/formal_c1_review.json` 記錄面板定位、評核日期及已存在的研究決定。固定面板需綁定原政策、六構面候選、準則版、正式事前選擇決定及審核人。每一筆 `gate_evidence_bindings` 將專案、範圍、正式截日、Gate、必需的各子主張連到上表的來源證據 ID 與同一上游簽核。五個科學 Gate 的子主張及上游欄位對應在 `formal_cohort.REQUIRED` 和 `METADATA`。WINDOW 須有經濟研究、澳洲範圍、截日時活動與 pre-FID 的明示證據。JORC 各分項採同一估算，GIS 須具代表幾何、各官方圖層與距離 QA。正式 PANEL 對每項原準則檢查變數、單位、基準與版本。正式 PASS、HOLD 與 EXCLUDE 均須可核對原件與有效的研究者簽核。目前收錄的簽核表及核准 crosswalk 都沒有實例。測試用肯定案例只存在於測試檔案。
