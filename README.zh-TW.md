# Alexa Voice Events

[English](README.md)

將 Alexa 語音事件交給 Home Assistant 自動化處理。選擇官方 Alexa Devices 已登入的帳號與音箱，再用 Blueprint 或 HA 自動化設定口令與動作。

## 開發狀態與支援版本

**v0.1.0** 已於 2026-10-21 通過自動檢查及限定範圍的 Marshall Uxbridge 實機驗收。多帳號、多音箱與恢復功能有軟體測試；其他音箱仍需明確同意試用，並維持未驗證。精確版本、實測內容與限制見 [驗收報告](docs/hardware-acceptance.md)。

需要 **HA Core 2026.10.2**、官方 **Alexa Devices** 與 **aioamazondevices 16.3.2**。先完成官方整合登入。本整合重用其 API，不要求另一組憑證，也不開第二條連線。其他版本須經重新審查與測試；不要為本整合降級 Core。

## 尚未正式發布的中止與回覆

開發版新增「嘗試中止原生回覆」、HA 模板回覆與唯讀官方目標解析；**v0.1.0 不包含這些功能**，固定開發候選已取得限定實機結果：來源 Speak 與既有家電動作通過，原生中止仍不可靠；已送出的播報可能先播完，才聽到後來的原生回答。Announce 及其他音箱仍未驗證，見[硬體紀錄](docs/hardware-acceptance.md)。詳細設定、API 與限制見 [英文說明](docs/replies.md)。

採用新版 Blueprint 後，中止預設開啟，也可能停止音樂；可在每個自動化關閉。回覆文字可留空，預設用 Speak 回到本次發話音箱，也能另選單台音箱，Announce 在進階選項。A 發話、B 回覆時只中止 A。更新 HACS 整合不等於更新匯入的 Blueprint，兩者需使用同一固定 commit，變更前保存原 Blueprint 與自動化設定。

順序是嘗試中止→家庭 actions→回覆模板求值。每個受管理步驟前重查本次來源／最新事件、接收／session、帳號與來源／接收時間未滿 15 秒；較新的同源事件即使不匹配，也會使尚未開始的舊步驟失效。已開始的使用者 actions 不強制中止；結束時若過期或撤權，剩餘回覆不補做。15 秒不是感測值採樣期限或呼叫／播完超時。

Stop 目標缺少或呼叫報錯，不阻擋仍有效的家庭 actions 與回覆；家庭 actions 未處理錯誤則跳過原定回覆。目標不明不猜測、不換音箱，空白／錯誤格式不念出，已完成家電動作不回滾。每 run 至多一次受管理 Stop／notify，不加 Blueprint 重試、固定播完等待、文字 stop 備援、全域排程或 Spotify 恢復。

`resolve_targets` 只回傳 registry 目標與固定原因；source_valid 只表示目前身分綁定，不是舊事件的執行授權，也不發聲或連 Amazon。官方呼叫返回只表示本機呼叫／入列，不能當成雲端送達、停止追問或播完；上游本身仍可能重試 HTTP。已入列命令無法撤回，未到 HA 的較新發話無法提前知道，跨自動化共用音箱仍可能重疊。其他音箱、中止追問、Speak／Announce 與自我辨識效果需分別驗收，不能沿用接收測試宣稱已通過。

### 用任意感測器建立查詢

從同一版本 Blueprint 建立自動化，選來源語音事件、逐行填辨識口令，純查詢的 Actions 可留空；在 Reply message 填 HA 模板，Reply speaker 留空就是本次發話音箱。感測實體、單位、格式及缺值句型都在家庭模板調整，無須改整合或增加型號規則。[英文設定範例](docs/replies.md#adapt-a-sensor-query-without-changing-the-integration)示範任意感測器的有限數字／單位檢查。

先檢查有效性再轉數字；unknown／unavailable、不存在、非有限值或單位不符不補成 0，真的 0 仍可有效。多項讀值可部分回答並明說缺值；使用 Home Assistant reports 表達 HA 記錄，不以一般 state 時間冒稱採樣時間。在 HA 模板編輯器唯讀預覽，不修改現役感測器 state 製造錯誤。

遷移前保存元件、實際匯入的 Blueprint 檔案、受影響自動化及啟用狀態；停用重疊消費者後，元件與 Blueprint 切換到同一固定建置，檢查設定並逐個啟用。回復時三者一起還原，不能只降元件而留下新版 Blueprint 對新動作的依賴。保留無關整合與家庭腳本；模板預覽不等於實際播報／中止成功。

## 安裝

選擇一種方式：

- **手動：**下載專案，僅將 `custom_components/alexa_voice_events` 複製到 HA 設定目錄的 `custom_components/` 下（通常是 `/config/custom_components/alexa_voice_events`），重新啟動 HA。
- **HACS 自訂儲存庫：**HACS → ⋮ → 自訂儲存庫，新增 `https://github.com/vincent97277/ha-alexa-voice-events`，類別選 **Integration**，下載 Alexa Voice Events，再重新啟動 HA。本專案未加入 HACS 預設商店；需要固定版本時選正式 tag；若改選預設分支，則是會隨開發更新的程式。

在 HA → 設定 → 裝置與服務 → 新增整合，選 **Alexa Voice Events**，選取既有 Alexa Devices 帳號與音箱。每個帳號最多一個項目，可選多個音箱；其他帳號另加項目，不能跨帳號選音箱。

本版以 Core 2026.10.2 為目標。可下載 [v0.1.0](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.1.0)，或供手動安裝的 [原始碼壓縮檔](https://github.com/vincent97277/ha-alexa-voice-events/archive/refs/tags/v0.1.0.zip)。另記安裝 tag／commit，不能只看 manifest 版本。正式版的元件與 Blueprint 和實機測過的 `85e21d4` 完全相同，其後只有發行文件更新；先前 `4944eea` 為 Core 2026.10.1 歷史基準。版本差異見 [相容性查核](docs/compatibility.md)。

## 設定與日常使用

整合的「設定」可新增／移除音箱或調整接收方式。`native` 接收官方整合更新；`volume_push` 由對應音箱推送觸發歷史讀取，沒有閒置輪詢與手動試驗視窗。

Marshall Uxbridge 依已記錄的 Uxbridge 查核建議 `volume_push`，首次選取會啟用；這不代表其他實體音箱或接收方式已驗證。未知音箱預設 `native`；未知音箱或覆寫已知設定時，須勾選 **Explicitly allow this unverified speaker / method** 才能啟用。接收開關不能繞過同意。診斷的 `validation_scope` 為 `uxbridge_volume_push` 或 `unverified`。實機範圍由 [驗收報告](docs/hardware-acceptance.md)記錄，不再在每個安裝中寫死 pending 標記。

每個音箱有接收開關、語音事件及診斷感測器，關閉、移除或更改方式只撤銷該音箱舊 session。接收意圖可跨重新啟動保存；關閉後不會自行開啟。帳號/API 重新連線會換新 session，還原的舊事件不會觸發動作。狀態包含 `disabled`、`ready`、`waiting`、`error`、`unsupported`；`ready` 只代表本機準備完成。

相容路徑每次最多兩個請求、每個最多二十秒，共用帳號 worker 並保留來源身分。失敗後等待 30／60／120／240 秒（上限 240 秒），五次連續失敗轉為 `error`；需期限後的新推送才重試，成功空結果亦重設失敗次數。沒有自主歷史重試輪詢。帳號狀態以 HA 通知與每五秒的本機 API 身分檢查觀察。結構不支援或 hook 所有權衝突會停止受影響路徑，保留官方整合；錯誤為固定代碼，不洩漏原始例外。更多狀態與復原細節見 [English README](README.md#current-behavior)。

## 匯入 Blueprint

HA → 設定 → 自動化與場景 → Blueprint → 匯入，貼上：

```text
https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.1.0/blueprints/automation/alexa_voice_events/phrase_to_action.yaml
```

匯入與整合安裝彼此獨立，不會自動建立家庭自動化。從 Blueprint 建立自動化，選音箱的語音事件、每行填一個完整口令，再選 HA 動作。比對會去除首尾空白、合併空白並轉小寫；若實際文字含 `alexa`，口令也要包含。複雜情境用 HA 自動化；官方 Alexa Devices 的播報等動作可直接在 HA 使用。

預設 `queued`、`max: 10`，可在建立後的自動化 YAML 調整。排隊動作執行前重新檢查十五秒內的新鮮度、接收開關與 session；已執行中的任意使用者動作由 HA 管理。切換家庭動作時停用重疊的舊接收者，避免重複執行。

語音文字遵循 HA recorder 政策，無額外歷史資料庫。家庭場景、裝置品牌的家庭規則、碼表量測及音樂恢復均交給 HA。v0.1.0 正式版執行程式已透過 HACS 安裝到測試的 Uxbridge 環境並經確認，精確版本與限制見驗收報告；排錯先看接收狀態／錯誤，再到 [issues](https://github.com/vincent97277/ha-alexa-voice-events/issues) 提供版本與重現步驟，遮蔽語音及帳號／裝置識別資訊。

## 開發與授權

測試環境：Python **3.14.6**、HA **2026.10.2**、pytest-homeassistant-custom-component **0.13.373**、aioamazondevices **16.3.2**；精確相依版本記於 `uv.lock`。

```sh
uv sync --locked
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

測試使用真實 HA 設定、實體生命週期與自動化／Blueprint 引擎，以及上游 coordinator／dispatcher／parser；控制遠端回應、時鐘與官方 Stop／notify 服務邊界，不呼叫 Amazon 音箱；禁用外部 socket，使用合成資料。這證明軟體行為，不代表 Amazon 傳遞、實體動作或其他音箱已驗證。CI 另以 hassfest 與 HACS action 驗證封裝；HACS 的品牌商店檢查不適用自訂儲存庫，因此略過 `brands`。

[Apache-2.0](LICENSE)，來源與第三方歸屬見 [NOTICE](NOTICE)。測試執行安裝的相依套件，未散佈上游 parser 摘錄或家庭錄音。相容邏輯由原本本機實作重構，已移除家庭依賴。
