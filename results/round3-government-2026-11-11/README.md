# 第三輪 VIC／TAS 官方資料取得

僅讀官方目錄及目錄明載的服務。共 11 次 HTTPS 請求。所有原始回應、時間、URL、SHA256及狀態見 request_log.json／acquisition.json。

VIC：DataVic 的 Mines and Mineral Occurrence Sites，官方標示 CC BY4.0，詮釋資料更新2026-11-08。經官方 WFS capabilities 與 DescribeFeatureType確認欄位及 CRS，按 siteid 排序取得全部18,794筆原生點；4頁完整、ID唯一、末頁無next。欄位子集保留名稱、專案、商品、座標、datum及精度；無operator欄。服務宣告非交易式分頁，因此只聲稱本次已核對總量、連續偏移及排序唯一性。

候選名稱不能直接視為REE專案：Wimmera同名是金礦；Donald／Nowie僅標Heavy minerals，Cannie標鈦鋯礦物，須保留身分與REE證據限制。已有座標的專案不覆寫。

TAS：官方MRT首頁HTTP403，立即停止，沒有重試、替代端點、登入或繞過限制。不能將無法取得資料寫成沒有專案。

TAS403回應含網站防機器人挑戰參數，原始回應完整保留於本機忽略目錄並記錄原SHA；提交內容只含明示的錯誤摘要衍生檔（HTTP狀態、頁面標題、原SHA及轉換說明），另有自身SHA，沒有登入／挑戰參數。這不是資料集原件，也不作為任何補值依據。

每次請求與資料集receipt均綁定研究者核准決定 round3-vic-tas-official-20261111，並記載版本：WFS2.0.0、capabilities updateSequence24781、目錄詮釋資料更新日；資料頁另保存原始timeStamp。導覽頁與403失敗不虛構資料集版本。
