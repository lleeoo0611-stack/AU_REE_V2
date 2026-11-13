# 第五輪任務 3

WA 僅移除 sortBy，沿用精確原件礦權號與 25 km 限制；其他州不嘗試。

新增 0 格，變更 0 項，待審 12 項。兩次完整離線來源重建逐位元一致，完整測試通過。既有填值、provenance、Census、inventory、凍結結果及 INCOMPLETE／CONTINUE 不變。
三種覆蓋率與分層分子分母見 summary.json。不為預估新增量放寬條件。

## 未新增原因（逐列／頁）
- {"candidates": "[]", "details": "{}", "project": "Mukinbudin REE Project", "project_id": "AU-3eaa906d8230334ef698", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Merredin REE Project", "project_id": "AU-81b21bdd06796fa2217d", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Peak Charles REE Project", "project_id": "AU-b31d00e2272ffa6ccbd3", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Rocky Gully Scandium–REE–Gallium Project", "project_id": "AU-d0827cf51def7e0014fc", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Grass Patch REE Project — OD6 tenements", "project_id": "AU-1c907e00c797bf8b3ce1", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Southern Cross Li-REE Project — GCX", "project_id": "AU-d99cf357d160df73387c", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Arunta West REE Project — Norwest", "project_id": "AU-c4391f8d2a6690076436", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Barballin REE Project", "project_id": "AU-b3ae34ac85d16018bd4b", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Munbinia REE Project", "project_id": "AU-f81823bd8ba271840345", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Wandagee REE Exploration Project — Consolidated Zinc", "project_id": "AU-b50a5b57669586191c33", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "North Dam Li–Nb–REE Exploration Project — CuFe", "project_id": "AU-cefbde90dc34312547d3", "reason": "not well-formed (invalid token): line 1, column 0"}
- {"candidates": "[]", "details": "{}", "project": "Perenjori Uranium–REE Exploration Project — HRE", "project_id": "AU-794821a2df9b7a244f96", "reason": "not well-formed (invalid token): line 1, column 0"}

## WA 實際結果

HTTP 200 但缺少 numberMatched，無法驗證完整性；僅 1 次請求，新增 0 格，12 列不填。沒有再改參數或重試。空 features 不代表已完整查無礦權。原始回應與詳細說明見 acquisition/README.md；parser 的 invalid token 不是 HTTP 400。
