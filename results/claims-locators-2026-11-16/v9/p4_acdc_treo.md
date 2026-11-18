# P4：ACDC 已公布原礦 TREO 品位與 partial 模式

只讀診斷；本輪沒有更動 src 或 claims。

## 現有宣告

ACDC 已宣告原礦 TREO 品位，原值保留如下；礦石量同為 620 Mt。兩者配對的 620 × 0.0584 × 10 = 362.08 kt 是計算結果，不是新增原件數值。

```json
{
  "variable": "grade",
  "value": 0.0584,
  "unit": "%",
  "basis": "TREO",
  "source_key": "goschen_central_mre2024",
  "source_sha256": "22016f67e614f73963e5a2252e0ec78184ed3906d668649e0dbdb17c365dba59",
  "pdf_page": 3,
  "page_markers": [
    "Total",
    "620",
    "584"
  ],
  "original_token": "584",
  "cell_binding": {
    "mode": "native_cell",
    "field": "grade",
    "basis": "TREO",
    "scope": "Goschen Central ACDC EL5278 global Indicated+Inferred resource at 1% total HM cutoff, 3 December 2024; 620 Mt dry bulk ore; TREO includes Y2O3. Oxides in Appendix1 are percentages of HM, not bulk ore. Excludes 2% HM nested subset, VHM Goschen Areas1-4, Ore Reserves and scheduled feed.",
    "page": 3,
    "original_unit": "ppm",
    "table_bbox": [
      48,
      501,
      563,
      611
    ],
    "row_bbox": [
      48,
      598,
      563,
      611
    ],
    "column_bbox": [
      518,
      501,
      563,
      611
    ],
    "table_label": "Table 2: Goschen Central Project Magnet Rare Earth assemblage at 1% Cut-off; for full results refer to Appendix 1.",
    "table_label_bbox": [
      49,
      502,
      464,
      514
    ],
    "row_label": "Total",
    "row_label_bbox": [
      54.6,
      598.7,
      73.8,
      609.8
    ],
    "column_label": "TREO",
    "column_label_bbox": [
      531.8,
      538.7,
      552,
      549.8
    ],
    "unit_bbox": [
      533.3,
      553.7,
      550.4,
      564.8
    ],
    "scope_anchor_bbox": [
      531.8,
      538.7,
      552,
      549.8
    ],
    "scope_anchor": "TREO",
    "section_id": "p3-grade"
  },
  "statement_id": "goschen-central-total-20241203",
  "scope": "Goschen Central ACDC EL5278 global Indicated+Inferred resource at 1% total HM cutoff, 3 December 2024; 620 Mt dry bulk ore; TREO includes Y2O3. Oxides in Appendix1 are percentages of HM, not bulk ore. Excludes 2% HM nested subset, VHM Goschen Areas1-4, Ore Reserves and scheduled feed.",
  "effective_date": "2024-12-03"
}
```

## 為何三格被抑制

census.py 的 summary_partial_bundle 只組 value={ore_mt: ...}，沒有 grade_pct 或 contained_treo_kt；summary_resource_fields 的「有TREO資源估計」又以 if not partial 才輸出。所以即使觀測中有原礦 grade，它也依整個 partial 模式的設計被略過。這不是品位宣告不存在，也不是此三格只差頁面標記。

## 最小可審查方案

現行程式沒有讀取可例外保留原礦 TREO 的旗標，只加資料欄位不會改輸出。需另核准一個明確選填旗標，例如 include_reported_bulk_treo_grade；只有旗標為真、現有已驗證的原礦 grade 與 ore 在同 SHA／statement／scope／effective_date 配對、且原礦基準與單位成立，才沿用完整 resource_bundle 規則產生 grade 與 contained TREO，再保留 HM 氧化物的既有換算。完整資源旗標也只能在這個完整配對成立時輸出。

估計 **8–14 行 src**（partial bundle 受控合併約 5–9 行、完整資源旗標條件約 1–2 行、失敗防護與說明約 2–3 行），另有 claims 選填旗標與測試。不是保證已能在此估計內完成，本輪不套用、不佔用 P6 的實作。

## Wimmera 防護

預設旗標不存在時逐格輸出與第 8 版完全相同；Wimmera 沒有已公布且驗證的原礦 grade，不能走例外。測試須涵蓋：(1) Wimmera 全 51 欄等於第 8 版 CI；(2) ACDC 旗標關閉時全欄等於目前；(3) 有旗標但缺 grade／基準非原礦／不同 SHA 或 statement 時拒絕輸出；(4) 合法配對時只恢復 ACDC 的品位 0.0584、總量 362.08 與完整資源旗標，15 個 HM 氧化物保持不變。

預估最多可恢復原來三格 SAME；仍以未來核准後 CI 為準。只把 HM 量與氧化物分布當作完整 TREO 總量會違反目前合約，本方案不這樣做。
