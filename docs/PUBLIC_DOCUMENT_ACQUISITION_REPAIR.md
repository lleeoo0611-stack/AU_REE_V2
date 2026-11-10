# 八項公開文件取得修復

延續 `experiment/asx-public-acquisition-20261109` 的 `48d0849` 基準，只處理原受阻清單8項作品。這不是完整第21輪，不增加連續零增量輪次。研究截止日2026-11-05、93×53、1944已填／2985空白、codebook DRAFT與既有空白分母規則均保留。原件不公開，既有成果不回退。

## 取得流程與界線

`config/public_acquisition_repair.json` 從既有blocked_acquisitions建立，保存原URL、action_id、研究列、可能影響欄位與人工途徑。只從已觀察的官方入口／公開發行人連結取得，不猜下載位置或私有endpoint。VIC2024核對舊封存SHA與capture receipt後重用；原URL受阻與同版內容已可用分開記錄。

共用 `acquisition.PublicDownloadSession` 使用既有urllib client的研究識別，正常CookieJar、真實入口Referer、預設TLS驗證、受限重新導向、gzip與串流。先寫staging，再驗證PDF檔頭、EOF、兩種解析器、全部頁面及頁數，通過才移入內容雜湊快照。HTML挑戰／錯誤頁不能成為PDF；掃描件保留原件並標記既有OCR／人工路徑，不自動成為觀測。舊request()介面與驗證條件不變。

設定上限：每網域1個工作、全域最多2個（實作依序1個）；連線10秒、讀取18秒、單次HTTP工作40秒、整個作品工作90秒；PDF最多64MiB、入口HTML最多3MiB；暫時錯誤最多重試2次，退避2／4秒；網域間隔2秒。Retry-After不能提前重試，超預算寫next_retry_at。HTTP同域兩次明確拒絕後暫停；正常瀏覽器一旦明確拒絕即停該域。403不重送相同請求，未收到HTTP回應不記403，原因未明不稱已確認WAF。

外層作品程序限制DNS／頁首／解析超時。中斷後先查已提交的完整文件receipt；結果不明時標記待核對，不盲重送。快取檢查SHA，完成或受阻路徑重跑不重複下載、建立來源或填值。改由新正常公開入口的嘗試需保留既有紀錄，不清除拒絕狀態後無限重試。

## 正常瀏覽器

桌面瀏覽器工具初期在kernel資產初始化失敗，沒有網站回應，並非403。之後安裝免費Playwright1.65.0，使用機器原有Microsoft Edge（實際157.0.4341.42），沒有安裝新瀏覽器。TLS驗證與Chromium sandbox保持開啟；匿名新context，不借用個人登入，不偽裝指紋，不解CAPTCHA，不輪換代理、不改平台網路限制。Apify保持停用，沒有付費來源或actor。

入口等待domcontentloaded後，下載連結另有最多10秒且受剩餘總預算約束的JavaScript等待。只點頁面實際連結，以expect_download／download event保存附件；頁內PDF另外擷取實際PDF response。只有HTTP200、格式完整且大小可控的PDF進快照；403、503、206、未知長度或額外壓縮的瀏覽器PDF不直接入庫，後者交由有界串流HTTP或人工流程。所有response保留實際狀態、轉向鏈、final URL、Content-Type、Retry-After；429／503寫next_retry_at，不提前重試。

可選context.request預設false；啟用時只用頁面實際連結與同context自然取得的cookies，獨立記錄HTTP行為及手動可稽核的轉向鏈，不宣稱與瀏覽器網路相同。登入、付費、人機驗證、TLS警告或明確拒絕不自動通過。可在新環境依序安裝與執行：

```powershell
.venv/Scripts/python.exe -m pip install -e ".[browser]"
$env:PYTHONPATH='src'
.venv/Scripts/python.exe tools/repair_public_documents.py run --config config/public_acquisition_repair.json --out work/public-acquisition-repair/assets
.venv/Scripts/python.exe tools/repair_public_documents.py browser --config config/public_acquisition_repair.json --out work/public-acquisition-repair/assets
```

同一out會重用快取／暫停狀態，不會因重跑而重送403。Edge須本機已存在；不要執行playwright install去覆寫使用者瀏覽器。其他正常已安裝browser channel由設定明確指定。

## 版次與人工匯入

`config/public_acquisition_identity_reviews.json` 是文件身分審查，與研究者codebook核准完全分開。核對發行機關、原文標題、發布日／月精度、報告識別、版本、頁數及關鍵章節，每項綁定原生頁面text SHA。日發布日期另綁定同作品官方入口與實際下載連結。資源有效日未載時保持UNKNOWN，不以發布日或報告涵蓋期替代。

同SHA只證明同一位元組。雜湊不同的替代件不能只因同標題／年度而合併：須有已核對參考原件、明確版本、全文及指定關鍵頁render比較；缺參考或內容不同保持待審。TAS的27Nov2025與18Dec2025檔名版本不能自動視為相同；Voyager的Oct2024涵蓋期不能當Jan2025報告發布日；Fingerboards表格模板Version7/March2020不能當專案2026referral日期。翻譯、新版或其他報告不能冒充舊原件。

人工正常下載後，複製 `config/public_document_manual_import.example.json` 至工作目錄，填實際原URL、來源URL、取得日／方法、出版社、標題、發布資訊與版次，然後：

```powershell
.venv/Scripts/python.exe tools/repair_public_documents.py import --config config/public_acquisition_repair.json --out work/public-acquisition-repair/assets --action-id TAS-Voyager-October2024-original --file C:/path/to/normal-download.pdf --metadata work/manual-source.json
.venv/Scripts/python.exe tools/repair_public_documents.py verify-identities --config config/public_acquisition_repair.json --out work/public-acquisition-repair/assets --reviews config/public_acquisition_identity_reviews.json
```

第二個命令只重驗已建立的身分proof；新匯入件須另外完成相應proof，不會因import而核准。缺metadata、壞檔或身分不明不轉正式觀測。不自動寄信索件。source_id沿用內容SHA，downloads.json與不可變快照可交給既有source-review／匯出管線；**取得與文件身分核對都不是科學欄位核准**。

填空白仍須既有asx_source_reviews等檢查：同案、資源範圍、版本、資源類別、截止品位、REO basis、單位、有效日、原值、頁碼／表格與轉換。衝突保留新證據供審查，不覆寫舊值；不以鑽孔或選冶樣比例乘全案TREO。codebook核准欄不填，不將無選定資源量整批改成不適用。本次沒有新值，現有53欄表與field_provenance全部未變。

## 結果、限制與重建

交付在 `results/public-acquisition-repair-2026-11-11/`。新取得REMP2025原件27頁、重用VIC2024官方同版副本36頁；新增原始／衍生／文字或分類格皆0，分母變動0。覆蓋率仍1944/4929=39.44%，調整後1944/4806=40.45%。REMP中的投資額、件數、其他商品產能與既有階段不當成新REE資源／年產資料。研究列不等於獨立礦案，Yttria／MtStirling重疊不加總，ASX同碼同名／已證別名合併規則未改。

**首輪真實Edge診斷未保存轉向鏈，該部分明寫UNKNOWN，不推定為空。最終版本已補齊並用本機夾具驗證，沒有為了補log額外重試403網站。** 兩份可用PDF由HTTP或已封存副本取得，HTTP redirect／版本／SHA證據完整；沒有把不完整瀏覽器log用於新數值核准。其餘來源的正常瀏覽器仍403或依網域暫停，人工途徑逐項列出。停止不代表來源窮盡；完整輪新增0，連續零增量仍1，不能計為完整第21輪或第二個零增量輪。

可離線重播（需已存本機原件，out-prefix及報告目錄需新建）：

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_public_document_repair.py tests/test_asx.py tests/test_capture_limits.py tests/test_discovery_eligibility.py
.venv/Scripts/python.exe tools/rebuild_asx_census.py --census-root ../AU_REE_V2 --out-prefix work/public-repair-new-replay
.venv/Scripts/python.exe tools/verify_engineering_baseline.py
.venv/Scripts/python.exe tools/report_public_document_repair.py --work work/public-acquisition-repair --out work/public-repair-new-report
```

首輪基準已兩次重建，四CSV與當前投影一致。完整相關回歸426項／353子測試通過，原405項皆涵蓋；最終取得專項測試數字與零失敗收據見交付目錄。實際快取重跑證明額外網路請求0、來源0、填值0。原PDF、HTML、SQLite、Cookie與搜尋全文只留本機，公開的是必要URL、hash、診斷與審查收據；不聲稱遠端CI有原件可重播。
