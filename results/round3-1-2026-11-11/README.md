# 第三輪任務 1

新增 0 格；變更／刪除空白分類 1891 格。

刪除兩個原本全空欄位，只重分類空白。Wimmera/WIM100 雖無 TREO 總量，仍有已選礦石資源量，因此實測有MRE38列／無MRE55列，與題示估計37／56不同。第2層已填資源格同時計入分子及分母。被刪欄及每格分類變更見 changed_cells.csv。NOT_APPLICABLE_NO_MRE_IS_DENOMINATOR_CONVENTION_NOT_PROOF_OF_ABSENCE

兩次獨立完整離線來源重建；四份CSV、summary及audit逐位元一致，完整回歸通過。Census、inventory、凍結歷史與INCOMPLETE／CONTINUE結論不動。

資源欄明確清單：
- 礦石蘊藏量_Mt
- TREO品位_pct
- 總TREO蘊藏量_kt
- 磁鐵稀土氧化物蘊藏量_kt
- 磁鐵稀土佔TREO_pct
- NdPr蘊藏量_kt_需兩者皆公布
- 完整重稀土組合蘊藏量_kt_需8元素皆公布
- 預估年產TREO_t_per_year
- 預估年產NdPr_t_per_year
- 有TREO資源估計
- 已公布元素數_共15項
- 已公布元素總和_kt
- 元素總和/TREO
- 元素數據一致性檢查
- 四項磁性元素皆公布
- 磁性元素重算值_NdPrTbDy_kt
- La2O3_氧化鑭_kt
- CeO2_氧化鈰_kt
- Pr6O11_氧化鐠_kt
- Nd2O3_氧化釹_kt
- Sm2O3_氧化釤_kt
- Eu2O3_氧化銪_kt
- Gd2O3_氧化釓_kt
- Tb4O7_氧化鋱_kt
- Dy2O3_氧化鏑_kt
- Ho2O3_氧化鈥_kt
- Er2O3_氧化鉺_kt
- Tm2O3_氧化銩_kt
- Yb2O3_氧化鐿_kt
- Lu2O3_氧化鎦_kt
- Y2O3_氧化釔_kt

第2層一般欄：
- 專案ID
- 開發商
- 未上市公司
- 專案名稱
- 所在地_中文
- 所在地_英文
- 國家
- 州省地區
- 緯度
- 經度
- 礦床型態代碼
- 礦床型態
- 開發階段代碼
- 開發階段類別
- 開發階段
- 產品/產出
- 有來源文件
- 資料來源名稱
- 資料來源URL
- ASX代碼

驗收：922項測試、546項subtests通過。changed_cells.csv的old_value／new_value在本任務表示空白分類或欄位刪除標記，不是主表中的既有數值；實際填值與field_provenance.csv逐位元不變。共1705個空白重分類、186個空白欄位格刪除；兩層實測第2層沒有已填資源格，題示約23格的差異來自Wimmera歸入有已選MRE層。
