# 八項受阻作品取得修復

本次是取得專項，非完整第21輪。研究母體、截止日、既有值與來源、分類DRAFT及分母規則均未改。

| 作品 | 本次原URL HTTP | 正常Edge流程 | 同版內容 | 人工途徑 |
|---|---|---|---|---|
| NT REE October2025 | 403 | NORMAL_BROWSER_HTTP_403_NO_BYPASS | 未取得合格同版件 | 由正常瀏覽器／發行機關／官方館藏取得原件後匯入；勿付費或繞限制 |
| REMP2025 | 200 | BROWSER_NOT_NEEDED_VALIDATED_BYTES_PRESENT | 新取得27頁 | 無；原URL已恢復 |
| TAS Prospectus18Dec2025 | 403 | NORMAL_BROWSER_HTTP_403_NO_BYPASS | 未取得合格同版件 | 由正常瀏覽器／發行機關／官方館藏取得原件後匯入；勿付費或繞限制 |
| VIC2024 Roadmap | 未重送；保留歷史403 | BROWSER_NOT_NEEDED_VALIDATED_BYTES_PRESENT | 重用36頁 | 內容已重用；原URL仍列受阻 |
| Wind Break EDGI May2024 | 未重送；保留歷史403 | BROWSER_NOT_REQUESTED_DOMAIN_PAUSED | 未取得合格同版件 | 由正常瀏覽器／發行機關／官方館藏取得原件後匯入；勿付費或繞限制 |
| Voyager EL32/2022 Oct2024 | 未重送；保留歷史403 | BROWSER_NOT_REQUESTED_DOMAIN_PAUSED | 未取得合格同版件 | 由正常瀏覽器／發行機關／官方館藏取得原件後匯入；勿付費或繞限制 |
| VIC Roadmap Update2026 | 403 | NORMAL_BROWSER_HTTP_403_NO_BYPASS | 未取得合格同版件 | 由正常瀏覽器／發行機關／官方館藏取得原件後匯入；勿付費或繞限制 |
| Fingerboards2026 referral | 403 | NORMAL_BROWSER_HTTP_403_NO_BYPASS | 未取得合格同版件 | 由正常瀏覽器／發行機關／官方館藏取得原件後匯入；勿付費或繞限制 |

新下載1份／27頁，重用1份／36頁，新增文件身分證據1、舊件重驗1；新科學觀測、原始數值、衍生格、文字／分類格及新增研究列皆0。原URL待處理8→7；同版內容尚未取得6項（包括Fingerboards，VIC2024內容已可用）。不是所有7項都在本次重新回應403。

1944/4929 = **39.44%**；依既有規則排除123格後1944/4806 = **40.45%**。分子、兩個分母及所有既有值／來源不變。

一般HTTP14個實際請求：5次200、9次403，包含入口頁；原PDF URL實際請求5個，其中REMP2025成功。Edge另外對4個官方入口收到403，另2項因同域暫停未發請求、2項已有核驗原件無須瀏覽器。這是特定受阻清單，不是一般ASX成功率。

403原因未確認，未宣稱WAF或文件撤除。MRT連續拒絕後暫停，Wind Break及Voyager本次沒有新直接HTTP或瀏覽器回應，歷史403保留。REMP這次正常會話成功，不能據此推定先前逾時根因。發行人一般文章中的隱藏CAPTCHA表單曾被誤判，已僅用封存HTML重新分類，未重送請求。

**限制：首輪真實瀏覽器的轉向鏈沒有被舊版介面保存，保持UNKNOWN，沒有推測為空。最終程式已補齊轉向鏈、動態連結有界等待及429/503 next_retry_at，且以本機夾具驗證；依限制沒有額外重試受阻網站。HTTP會話的轉向鏈與兩份可用PDF證據完整保存。**

同版核驗：REMP2025 SHA256 `c31024a4a94e94aa7bb0187a7c845975c43dc0c406ab9bba2a5a192e45825d73`，27頁，官方入口19December2025日期、PDF出版社／標題／ISSN1839-5007與p12關鍵內容核對。VIC2024 SHA256 `b4a882278894c26780c531beed947d35add62ec43d1918adc1ce218a1f58646e`，36頁，December2024與ISBN978-1-76136-595-9核對；只是原已存在的官方館藏副本，不能當成新下載或證明與受阻原URL位元組相同。

REMP p12主要提供投資、前FID及既有DFS資訊，p14–15為投資金額／件數；p13其他商品產能不轉填REE。既有精確日期與所選資源範圍保留，沒有以概略進度覆寫。VIC政策、區域圖示及測試坑資訊不等於全案MRE或年產。研究列不等於獨立礦案；Yttria／Mt Stirling重疊資源不加總。

| 測試 | 方法 | 子測試 | 失敗／錯誤／跳過 |
|---|---:|---:|---|
| acquisition-tests.xml | 49 | 23 | 0 / 0 / 0 |
| regression-tests.xml | 426 | 353 | 0 / 0 / 0 |

原405項全部包含於回歸且通過；方法聯集448，各組有重疊不可相加。兩次離線重建四CSV與當前投影一致；既有921份ASX歷史檔案及Census未改。實際重跑快取新增網路請求0、來源0、填值0。

完整逐項HTTP／瀏覽器紀錄見attempts.json；原URL與同版內容分開見source_results.csv、blocked_acquisitions_after_repair.json；文件SHA／版次證據見documents.json、document_identity_reviews.json；原欄值及不填理由見field_review.csv。原始PDF、HTML、Cookie、SQLite與搜尋全文均不公開。

可重跑命令與匯入方式見 [流程說明](../../docs/PUBLIC_DOCUMENT_ACQUISITION_REPAIR.md)。收斂policy未改，完整輪新增0，連續零增量仍1，維持CONTINUE；不能把這次局部0填值當成第二個完整零增量輪，也不能以STOP宣稱資料找齊。
