# Registry crosswalk: formal automated build

## 範圍與核對方法

- 正式基準：`b5e2a73438e2f3aa9f4adc3ab0f6ff0f898f0fca`。實驗身分規則來源：`980bedbcc250e720e1eab9c734032b5df72c3c39`。
- 逐列依既有 `store.digest([entity_namespace, str(id)])` 前 20 字元，加 `AU-` 重算。未另發 ID。
- 36 個正式 claims entity 全數保留；其中 29 個對應實驗，7 個正式獨有。新增 63 個 = 60 個 `ADMIT_PROJECT` 候選 + 3 個既有官方表 ID；對照總計 99 個 entity、實驗對應 92 個。
- 60 個候選：`config/asx_discovery_reviews.json` 的 `candidate_key`，套用 `reviewed_discovery.project_id` 之 `reviewed_project_extension_v1`。僅用於身分，不從該檔搬數值宣告。
- 3 個官方表 ID：`official.ingest_official_table` 對 `mount-ridley`、`splinter`、`mt-stirling` 使用 `WA_DMPE_REE_2026_PROJECT`。原始表為既有 `data/snapshots/ae76952cae874b34aa01430e042b5e85b0a983699f584383583bf9f2f4e1a56b.csv`，沒有讀取實驗結果 CSV。
- 63 個新增 ID 全部可重現；算不出的清單：空。208 筆來源審查紀錄所列 project_id 全部落在這 99 個 entity 內。
- 63 個中 59 個在來源審查紀錄有對應 review；4 個 Charley 歷史勘探專案沒有。這不授權新增其觀測值。

## 不得強行寫入的更名關聯

`same_project_renamed` 尚未寫入。提示詞稱 GoldArc 年報 p.13 是 Yttria 與 Mt Stirling 更名依據，但核准審查內容明確區分公司更名與專案範圍：

- `fullscope13_mt_stirling_yttria_mre20240416` 的 scope 指出 Asra → GoldArc/GA8 為 issuer 更名，並明示 `no new project or identity merge`。
- `researcher_rule_decisions.json` 的 `round4-issuer-merge-20261113` 規則是 `SAME_ISSUER_RENAME_RESEARCHER_APPROVED`，原決策文字亦為兩家公司視同改名。
- 正式 `data/identity_links.json` 已有 Mt Stirling → Yttria 的 `CONTAINS_DOCUMENTED_REE_SCOPE_NOT_IDENTITY_EQUIVALENCE`，引用 `yttria_maiden2024`，PDF p.1，日期 2026-11-03，來源 SHA `73936d124c5ce52038f968db521713ba86e72b92c847fb391254ebc47c0f0d51`。該關聯及兩個 entity 均原樣保留。
- `resolution.resolve` 的 typed relation contracts 沒有 `same_project_renamed`；只改資料會產生 `UNSUPPORTED_TYPED_RELATION`。新增支援要改本次不允許的 `resolution.py`，不能假稱純資料接線已完成。需研究者釐清是否只保留現有 scope 關聯，或另外授權有原件依據的 relation contract。

## 逐列對照

| AU-ID | 名稱 | namespace | native id | 對應方式 |
| --- | --- | --- | --- | --- |
| AU-0098e17a63e7c05c213f | Wudinna Rare Earths Project | SA_MINING_PROJECT_SITE_NO | 1123290 | 正式版與實驗線共同 |
| AU-02d486d425ca0792bdc5 | Comet REE Project | reviewed_project_extension_v1 | comet | 新增，審查專案 ID |
| AU-0832169526bb5ec07626 | Franklyn Kaolin–REE Project — Nackara Arc | reviewed_project_extension_v1 | franklyn | 新增，審查專案 ID |
| AU-0c085ce114ad2a4aa495 | Benmara prospect within Barkly | ISSUER_DOCUMENTED_PROSPECT | barkly-benmara | 正式版獨有，原樣保留 |
| AU-1103c5aa8bb63077ac61 | Hines Hill REE Project | reviewed_project_extension_v1 | hines-hill-wcn | 新增，審查專案 ID |
| AU-12cc237ae66c7a6508ca | Redlings Rare Earth Project | WA_DMPE_REE_2026_PROJECT | redlings | 正式版與實驗線共同 |
| AU-1345edd8165c10930e94 | Nolans Project | AUSTRADE_2026_REE_PROJECT | nolans-rare-earths-project | 正式版與實驗線共同 |
| AU-14f7cb8ca1fcd58f536c | Central Gawler REE Exploration Project — Indiana | reviewed_project_extension_v1 | central-gawler-indiana | 新增，審查專案 ID |
| AU-176852ef1348ac10d154 | Nowie Rare Earths and Mineral Sands Project — VHM | reviewed_project_extension_v1 | nowie-vhm | 新增，審查專案 ID |
| AU-1c907e00c797bf8b3ce1 | Grass Patch REE Project — OD6 tenements | reviewed_project_extension_v1 | grass-patch-od6 | 新增，審查專案 ID |
| AU-203b4d90e5c23a323610 | Harts Range REE–Nb Exploration Project — New Frontier | reviewed_project_extension_v1 | harts-range-nfm | 新增，審查專案 ID |
| AU-216d0983f6892f9b58f9 | North Stanmore Heavy Rare Earth Project | WA_DMPE_REE_2026_PROJECT | north-stanmore | 正式版與實驗線共同 |
| AU-2262a37ca19531f08da3 | Splinter Rock Rare Earth Project | WA_DMPE_REE_2026_PROJECT | splinter-rock | 正式版與實驗線共同 |
| AU-2a3a86a4d971e9f9838d | Brockman Project | WA_DMPE_REE_2026_PROJECT | brockman | 正式版與實驗線共同 |
| AU-2ab3e8eb7b5784e64f9b | Duke Rare Earth Project | reviewed_project_extension_v1 | duke | 新增，審查專案 ID |
| AU-2af694147ae21c393820 | Lake Campion REE Exploration Project — IGO | reviewed_project_extension_v1 | lake-campion-igo | 新增，審查專案 ID |
| AU-2cfeb25aefee0c4f95fb | Dubbo Project | AUSTRADE_2026_REE_PROJECT | dubbo-project | 正式版與實驗線共同 |
| AU-2fc429d0556dfa0b95c4 | Donald Rare Earth and Mineral Sands Project | AUSTRADE_2026_REE_PROJECT | donald-rare-earth-mineral-sands-project | 正式版與實驗線共同 |
| AU-329908ab8d4c1d1d3e03 | Avonbank Mineral Sands Project | reviewed_project_extension_v1 | avonbank | 新增，審查專案 ID |
| AU-3651cf8448b9227adcf5 | Mount Ridley | WA_DMPE_REE_2026_PROJECT | mount-ridley | 新增，官方表既有 ID |
| AU-3a0020b6daf659f62138 | Euston Mineral Sands Project | reviewed_project_extension_v1 | euston | 新增，審查專案 ID |
| AU-3eaa906d8230334ef698 | Mukinbudin REE Project | reviewed_project_extension_v1 | mukinbudin | 新增，審查專案 ID |
| AU-3eb7131e4daea18a60a0 | Sandy Mitchell Rare Earths and Heavy Minerals Project | reviewed_project_extension_v1 | sandy-mitchell | 新增，審查專案 ID |
| AU-410159af7b79ea498ec2 | Cannie Critical Mineral Project — VHM | reviewed_project_extension_v1 | cannie-vhm | 新增，審查專案 ID |
| AU-41ee0148c804293cfc39 | New Goldfield Li–REE Exploration Project — Cape | reviewed_project_extension_v1 | new-goldfield-cape-gdm | 新增，審查專案 ID |
| AU-4286ab9c245effb445ff | Burracoppin Project | WA_DMPE_REE_2026_PROJECT | burracoppin | 正式版與實驗線共同 |
| AU-430f216ca620b69af5f9 | Charley Creek South-East Project — historical URO EL33006 exploration | reviewed_project_extension_v1 | charley-creek-south-east-uro-el33006-historical | 新增，審查專案 ID |
| AU-435cac8afc319d50e811 | Vanadis prospect within Barkly | ISSUER_DOCUMENTED_PROSPECT | barkly-vanadis | 正式版獨有，原樣保留 |
| AU-447261eed0e81eae88bf | Goschen Central Rare Earths and Mineral Sands Project — ACDC | reviewed_project_extension_v1 | goschen-central-acdc | 新增，審查專案 ID |
| AU-47d12ebe6b66df8e5936 | Greater Brothers | WA_DMPE_REE_2026_PROJECT | greater-brothers | 正式版與實驗線共同 |
| AU-49b538453133bd968e8d | Koppamurra Rare Earths Project | SA_MINING_PROJECT_SITE_NO | 2298466 | 正式版與實驗線共同 |
| AU-4ec1fb08563b42352d29 | Cowalinya Rare Earth Project | WA_DMPE_REE_2026_PROJECT | cowalinya | 正式版與實驗線共同 |
| AU-524c37fc04cf47bf8dca | Balranald Mineral Sands Project | reviewed_project_extension_v1 | balranald | 新增，審查專案 ID |
| AU-557f0c9ad81bf84bbb6d | East Laverton REE Exploration Project — Pt Kidman area | reviewed_project_extension_v1 | east-laverton-mtm | 新增，審查專案 ID |
| AU-574465211976ec57b1ef | Splinter | WA_DMPE_REE_2026_PROJECT | splinter | 新增，官方表既有 ID |
| AU-5a557134d57805141647 | Boland prospect within Wudinna | ISSUER_DOCUMENTED_PROSPECT | wudinna-boland | 正式版獨有，原樣保留 |
| AU-5ea2535a2de9a1a3327e | Viper REE Project — EMU | reviewed_project_extension_v1 | viper-emu | 新增，審查專案 ID |
| AU-630885ed0d74d8641d6c | Bencubbin REE Project | reviewed_project_extension_v1 | bencubbin | 新增，審查專案 ID |
| AU-645024d708baf5b52bc2 | Cascade REE Project — Zinc of Ireland | reviewed_project_extension_v1 | cascade-zinc-of-ireland | 新增，審查專案 ID |
| AU-6898a8e4d5225785f507 | Head prospect within Wudinna | ISSUER_DOCUMENTED_PROSPECT | wudinna-head | 正式版獨有，原樣保留 |
| AU-68da41afe874c3bd66d4 | Voyager Rare Earth Project — Tasmania | reviewed_project_extension_v1 | voyager-lu7 | 新增，審查專案 ID |
| AU-6a5615e0ed95d955c2dd | iTech Eyre Peninsula REE–Kaolin Project | reviewed_project_extension_v1 | itech-eyre-peninsula | 新增，審查專案 ID |
| AU-6d807eb7caec9db0f35e | Goschen — Area 1 resource scope | AUSTRADE_2026_REE_PROJECT | goschen | 正式版與實驗線共同 |
| AU-6f0ecda27d291720036d | Nutgrove REE Project | reviewed_project_extension_v1 | nutgrove-ree | 新增，審查專案 ID |
| AU-70cc41e3a7106f983f73 | Lake Tay REE Project | reviewed_project_extension_v1 | lake-tay-wcn | 新增，審查專案 ID |
| AU-70fc8a7de18ad8209c32 | Charley Creek North-East Project — historical URO EL33000 exploration | reviewed_project_extension_v1 | charley-creek-north-east-uro-el33000-historical | 新增，審查專案 ID |
| AU-7135b2eb1d3f193da9a6 | Gilberton REE Exploration Project — ActivEX | reviewed_project_extension_v1 | gilberton-activex | 新增，審查專案 ID |
| AU-7157ac0201b7d1e93ff7 | Graceland REE Project — EMU | reviewed_project_extension_v1 | graceland-emu | 新增，審查專案 ID |
| AU-73183907b9a389385bc8 | Mount Ridley Project — Central Mia scope | project_registry_v1 | mount-ridley-mia | 正式版獨有，原樣保留 |
| AU-73549b8a9b1c6faf55eb | Coburn Mineral Sands Project | reviewed_project_extension_v1 | coburn-mineral-sands | 新增，審查專案 ID |
| AU-7537d9555628040fab40 | Fingerboards | AUSTRADE_2026_REE_PROJECT | fingerboards | 正式版與實驗線共同 |
| AU-75fe0f1a81005bd19586 | Durack REE–Ti–Zr Exploration Project — historical BPM option | reviewed_project_extension_v1 | durack-bpm-historical-option | 新增，審查專案 ID |
| AU-785536db5ff12c25350d | Circle Valley | WA_DMPE_REE_2026_PROJECT | circle-valley | 正式版與實驗線共同 |
| AU-794821a2df9b7a244f96 | Perenjori Uranium–REE Exploration Project — HRE | reviewed_project_extension_v1 | perenjori-hre | 新增，審查專案 ID |
| AU-7c198d219aa1db3e291f | Lyons | WA_DMPE_REE_2026_PROJECT | lyons | 正式版與實驗線共同 |
| AU-81b21bdd06796fa2217d | Merredin REE Project | reviewed_project_extension_v1 | merredin | 新增，審查專案 ID |
| AU-88dfe58aac214c33e576 | Aramac Rare Earth Element Project — ActivEX | reviewed_project_extension_v1 | aramac-activex | 新增，審查專案 ID |
| AU-8c5887498873bf838e09 | Coondina REE Project — historical MinRex drilling | reviewed_project_extension_v1 | coondina-historical-minrex-ree | 新增，審查專案 ID |
| AU-8f3fe174a998d20ee4cf | Mangaroon Project — Yin resource scope | WA_DMPE_REE_2026_PROJECT | mangaroon | 正式版與實驗線共同 |
| AU-908fd6f4461622e89548 | Yangibana Rare Earths and Niobium Project | WA_DMPE_REE_2026_PROJECT | yangibana | 正式版與實驗線共同 |
| AU-97137ef07af49e3607b2 | Charley Creek North Project — historical URO EL33004 exploration | reviewed_project_extension_v1 | charley-creek-north-uro-el33004-historical | 新增，審查專案 ID |
| AU-9b667066e6eb66753005 | Cummins Range Rare Earths-Phosphate Project | WA_DMPE_REE_2026_PROJECT | cummins-range | 正式版與實驗線共同 |
| AU-9bd8e5ed8408cd84d876 | Browns Range Project — Wolverine scope | project_registry_v1 | browns-range | 正式版與實驗線共同 |
| AU-9d967ecaac6e02fc76a5 | Rankin Dome Rare Earth Project | reviewed_project_extension_v1 | rankin-dome | 新增，審查專案 ID |
| AU-a8258e4989c7bd95b7af | Mt Clere Project — Tower resource scope | WA_DMPE_REE_2026_PROJECT | mt-clere | 正式版與實驗線共同 |
| AU-a9b72e86940271be45a3 | Diemals Li–REE Project | reviewed_project_extension_v1 | diemals-wcn | 新增，審查專案 ID |
| AU-ad64122c217f0dbfabc8 | Barkly Rare Earths Project | project_registry_v1 | barkly-ree | 正式版與實驗線共同 |
| AU-af44c2bd1173b453953f | Aileron Niobium–REE Project | reviewed_project_extension_v1 | aileron | 新增，審查專案 ID |
| AU-b2dadf9c8046c3c68a02 | Cascade Rare Earth Project — Meeka | reviewed_project_extension_v1 | cascade-meeka | 新增，審查專案 ID |
| AU-b31d00e2272ffa6ccbd3 | Peak Charles REE Project | reviewed_project_extension_v1 | peak-charles | 新增，審查專案 ID |
| AU-b3ae34ac85d16018bd4b | Barballin REE Project | reviewed_project_extension_v1 | barballin-wcn | 新增，審查專案 ID |
| AU-b50a5b57669586191c33 | Wandagee REE Exploration Project — Consolidated Zinc | reviewed_project_extension_v1 | wandagee-czl | 新增，審查專案 ID |
| AU-bb565f5348679a46d4a0 | Salazar Critical Minerals Project | WA_DMPE_REE_2026_PROJECT | salazar | 正式版與實驗線共同 |
| AU-c4391f8d2a6690076436 | Arunta West REE Project — Norwest | reviewed_project_extension_v1 | arunta-west-norwest | 新增，審查專案 ID |
| AU-c5e94422a89a23f82408 | Mt Craig Copper–REE Exploration Project — Taruga | reviewed_project_extension_v1 | mt-craig-taruga | 新增，審查專案 ID |
| AU-cae6c11543b0da5f840d | West Arunta Project — Luni Niobium–REE scope | reviewed_project_extension_v1 | west-arunta-luni | 新增，審查專案 ID |
| AU-cc4e217a90b7123dce0a | Kennedy Rare Earths Project | project_registry_v1 | candidate-b17e9292e0cb34972770 | 正式版與實驗線共同 |
| AU-cefbde90dc34312547d3 | North Dam Li–Nb–REE Exploration Project — CuFe | reviewed_project_extension_v1 | north-dam-cufe | 新增，審查專案 ID |
| AU-d0827cf51def7e0014fc | Rocky Gully Scandium–REE–Gallium Project | reviewed_project_extension_v1 | rocky-gully | 新增，審查專案 ID |
| AU-d0ce731e1d8198ffaf58 | Mt Stirling | WA_DMPE_REE_2026_PROJECT | mt-stirling | 新增，官方表既有 ID |
| AU-d1394abdef4c8d971c78 | Condingup REE Project | reviewed_project_extension_v1 | condingup | 新增，審查專案 ID |
| AU-d1aeb21e18e60fe8e32e | Deep Leads – Rubble Mound – Wind Break REE Project | reviewed_project_extension_v1 | deep-leads-rubble-mound-wind-break | 新增，審查專案 ID |
| AU-d1e3e2803f3c4287f6db | Charley Creek South Project — historical URO EL33054 and EL33055 exploration | reviewed_project_extension_v1 | charley-creek-south-uro-gr617-historical | 新增，審查專案 ID |
| AU-d28382dfa82f1664065e | Narraburra Rare Earths Project | project_registry_v1 | narraburra | 正式版與實驗線共同 |
| AU-d2cd77f89298d6dae330 | Mons Project — Block3 East resource scope | WA_DMPE_REE_2026_PROJECT | mons | 正式版與實驗線共同 |
| AU-d99cf357d160df73387c | Southern Cross Li-REE Project — GCX | reviewed_project_extension_v1 | southern-cross-gcx | 新增，審查專案 ID |
| AU-d9fb1b1e3e2ec9fa0851 | Charley Creek REE Project | reviewed_project_extension_v1 | charley-creek | 新增，審查專案 ID |
| AU-dac3c8e40326b8244cdb | Jupiter development study within Brothers | project_registry_v1 | jupiter | 正式版與實驗線共同 |
| AU-e4413e45c01b536895cb | Australian Strategic Materials Limited | issuer_v1 | asm | 正式版獨有，原樣保留 |
| AU-e50ba6a268ea89226495 | Achilles REE Project — Tambourah | reviewed_project_extension_v1 | achilles-tambourah | 新增，審查專案 ID |
| AU-e6d859a831ed5954b440 | Kenny Li–REE Exploration Project — EverGreen | reviewed_project_extension_v1 | kenny-evergreen | 新增，審查專案 ID |
| AU-ee34781b030807146e64 | Ravensthorpe REE Exploration Project — Young River, Dalyup and Bremer | reviewed_project_extension_v1 | ravensthorpe-mtm | 新增，審查專案 ID |
| AU-ee5ca893d12883df35f1 | Yttria REE Project | project_registry_v1 | yttria | 正式版獨有，原樣保留 |
| AU-efff91a06cf344122d88 | Mt Weld Project | project_registry_v1 | mt-weld | 正式版與實驗線共同 |
| AU-f46f6d53e7196650495d | Kalkaroo | SA_MINING_PROJECT_SITE_NO | 1130520 | 正式版與實驗線共同 |
| AU-f81823bd8ba271840345 | Munbinia REE Project | reviewed_project_extension_v1 | munbinia-wcn | 新增，審查專案 ID |
| AU-fb4e914f86102baa414a | WIM150 Rare-Earth-Bearing Mineral Sands Project — Australian Zircon 2015 | reviewed_project_extension_v1 | wim150-australian-zircon | 新增，審查專案 ID |
| AU-fe65cb1bd28eacb7a67f | Copi Mineral Sands Project | reviewed_project_extension_v1 | copi | 新增，審查專案 ID |
| AU-ff758cad5beb276d327d | Wimmera Mineral Sands Project — Iluka WIM100 | reviewed_project_extension_v1 | wimmera | 新增，審查專案 ID |
