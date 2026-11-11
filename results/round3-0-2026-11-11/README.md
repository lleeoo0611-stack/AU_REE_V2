# 第三輪任務 0

基線 cde12ab 已依先前「更新總表」指示發布第二輪 72 格，原53欄 2,141／4,929。本次不重複新增，也不改既有總說明及 provenance。重新從 Census 與封存來源兩次獨立完整離線重建 A/B/C-main/D，四份 CSV、summary、audit 逐位元一致；C-NT 拆出至任務3b，不將未通過 NT 驗收說成已完成。

三種覆蓋率列於 summary；51欄及兩層為本輪刪欄後口徑預覽，尚未改結構。第2層既有資源格同時計入分子與分母。Census、inventory、凍結結果、INCOMPLETE／CONTINUE 不變。

新工作樹重建另發現兩份設定檔的換行格式原本被Git正規化，造成凍結summary的設定SHA不符；已保留原本經核實的CRLF位元並加入.gitattributes保護。失敗重建沒有發布；修正後兩次完整重建及905項測試、546項subtests全部通過。
