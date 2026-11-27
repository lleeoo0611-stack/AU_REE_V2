# 第十階段歷史來源核驗

2026-11-13 歷史鎖定清單有 **715 份**不重複原件。本輪由來源或本機庫重開原始位元組核驗 **696 份**，其餘 **19 份**維持 `SOURCE_UNAVAILABLE`。

相同鎖定清單相較前一次原件庫多核驗 **28 份**。

登記來源取得使用 56 個請求額度。歷史 ASX 收據提供 27 個待重驗的公開網址，實際使用 28 個額度。每個網址依現行核准主機、robots、節流、重試及檔案大小規則取得，再核對鎖定 SHA。歷史 ASX 登記提案維持撤銷。

不計本輪 ASX 批次時，已核驗 669 份。ASX 批次另取得 27 份相符原件，共 120,855,730 bytes。原件置於執行工作庫，報告保留可重跑的官方網址、取回時間、檔案大小及原始 SHA。

未取得原件包括 PDF 13 份、政府 WFS 4 份、政府 CSV 2 份。同網址的新位元組另以實際 SHA 保存；歷史證據仍引用原 SHA。清單保留每個缺件的來源鍵、Project ID、版本、日期、原網址、嘗試網址與失敗類型。

既有歷史輸出直接引用缺件的範圍包括 **21 個 Project**、120 個 Census 欄位、21 筆資源觀測、3 筆影子候選與 0 筆 MCDA 準則來源鏈。直接牽涉 0 個面板，另列可能受影響的重選值範圍。歷史 C1 參照保留原義，現行正式 C1 依本輪 disabled 政策。

完整 93 案 2026-11-13 重建狀態為 `BLOCKED_MISSING_ASSETS`。

截日 **2026-11-05** 的 Phase 22 鎖檔共 303 筆快照，核驗 538／538 份必需原件。

可重播子集執行狀態為 `NOT_INVOKED`。

附入合法持有的先前資產庫後，可循現行政策重跑完整來源檢查。

```sh
python -m au_ree_v2.phase10_recovery --online --work work/historical-recovery \
  --library VERIFIED_ASSET_LIBRARY --out work/phase10-recovery-report
```

可獨立重取本輪已核驗的 ASX 批次供保存。

```sh
python -m au_ree_v2.phase10_recovery \
  --reacquire-archive-manifest results/phase10-2026-11-27/source_recovery_manifest.json \
  --out work/phase10-original-batch --request-budget 80 --timeout 10
```

[逐件狀態、來源與影響](source_recovery_manifest.json)
