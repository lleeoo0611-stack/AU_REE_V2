# WA 單次請求的完整性阻擋

只執行 1 次已核准的 WA GetFeature hits 請求。已移除 sortBy，其餘原請求參數與礦權過濾條件保留；resultType=hits 依提示詞加入。

HTTP 200 回傳有效 GeoJSON FeatureCollection，CRS 為 EPSG:7844，features 為空，但沒有 numberMatched。無法核對總筆數，不將空 features 當作「已完整查無礦權」，因此停止，不發出後續分頁請求，不再調整參數。

manifest.json 中保留原始解析例外（JSON 缺少 numberMatched 後嘗試 XML，產生 invalid token）。這不是 HTTP 400、不是登入限制，也不代表服務沒有任何匹配礦權。實際阻擋為缺少提示詞要求的 numberMatched 完整性證據。

原始回應 SHA-256：9d714ed19f48abd63ece1a2c480d6e03dddbedddb3fe34174b355b5da6da4fd8。

本輪 12 個候選專案均不回填座標；其餘州未重試。
