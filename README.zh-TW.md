# Alexa Voice Events

[English](README.md)

將 Alexa 語音事件交給 Home Assistant 自動化處理。選擇官方 Alexa Devices 已登入的帳號與音箱，再用 Blueprint 或 HA 自動化設定口令與動作。

## 開發狀態與支援版本

**v0.3.0** 簡化 Blueprint 回覆：選感測器即可自動產生回答，或填入自訂文字／模板。回覆固定以 Speak 送回本次發話音箱；Reply speaker／Reply mode 已移除，更新前請讀[遷移說明](docs/reply-simplification.md#updating-existing-automations)。感測器報告、既有模板、家庭燈光與原生問句有 [Uxbridge 限定驗收](docs/hardware-simplified-replies.md)。原生中止仍不可靠，這版不宣稱修復先前已呼叫 Speak 卻音訊不完整的問題；見[版本說明](docs/releases/v0.3.0.md)。

需要 **HA Core 2026.10.2**、官方 **Alexa Devices** 與 **aioamazondevices 16.3.2**。先完成官方整合登入。本整合重用其 API，不要求另一組憑證，也不開第二條連線。其他版本須經重新審查與測試；不要為本整合降級 Core。

## 中止與回覆

1. 從同版 Blueprint 建立自動化，選發話事件與逐行辨識口令，設定家庭 Actions；純查詢可留空。
2. 在 **Sensors to report** 選感測器，**Reply message** 留空，即可依 Actions 後的 HA 記錄值回答。
3. 需要自訂句型時填入 Reply message；非空文字／模板優先於感測器報告。可參考[數值模板](docs/replies.md#adapt-a-sensor-query-without-changing-the-integration)。
4. 要完全不播 HA 回覆，同時清空感測器與 Reply message。Stop 是獨立開關，**預設開啟**，也可能停止音樂。

感測器名稱與單位沿用 HA，生成文字以英文為主；不自動換單位、調精度或推測採樣時間。缺值與無效數值明說 unavailable，不補成 0；真正的 0 仍可有效。[簡單設定](docs/reply-simplification.md)與[完整動作及限制](docs/replies.md)提供細節。

口令選有明確語境的自然句子，核對 `voice_command`，再加入可接受的實際字面變體。HA 口令不會訓練 Alexa；沒有逐字稿、未匹配及已呼叫 Speak 卻沒完整聲音須分開排查，見[口令指南](docs/recognized-phrases.md)。

每個受管理步驟前仍檢查事件、session、接收與十五秒期限；已開始的家庭 Actions 不強制中止，已送往 Amazon 的命令無法撤回。服務返回不代表停止追問或播完。`resolve_targets` 的進階唯讀 API 保留，使用者仍可自行組合一般 HA actions。

更新前備份實際元件、Blueprint、所有消費者設定與啟用狀態；**HACS 不會更新既有 Blueprint**。舊 `reply_device`／`reply_mode` 不再影響新版 Blueprint，依賴跨音箱或 Announce 的自動化需先調整。回復時同步還原原版本及設定；本次不新增重試、固定延遲或語音糾字功能。

## 安裝

選擇一種方式：

- **手動：**下載專案，僅將 `custom_components/alexa_voice_events` 複製到 HA 設定目錄的 `custom_components/` 下（通常是 `/config/custom_components/alexa_voice_events`），重新啟動 HA。
- **HACS 自訂儲存庫：**HACS → ⋮ → 自訂儲存庫，新增 `https://github.com/vincent97277/ha-alexa-voice-events`，類別選 **Integration**，下載 Alexa Voice Events，再重新啟動 HA。本專案未加入 HACS 預設商店；需要固定版本時選正式 tag；若改選預設分支，則是會隨開發更新的程式。

在 HA → 設定 → 裝置與服務 → 新增整合，選 **Alexa Voice Events**，選取既有 Alexa Devices 帳號與音箱。每個帳號最多一個項目，可選多個音箱；其他帳號另加項目，不能跨帳號選音箱。

下載 [v0.3.0](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.3.0) 或[原始碼 ZIP](https://github.com/vincent97277/ha-alexa-voice-events/archive/refs/tags/v0.3.0.zip)。Blueprint 與實測候選 `88ad028` 相同，Python 行為沿用 v0.2.0，版本 metadata 為 0.3.0；候選 Blueprint 安裝不等於透過 HACS 安裝正式 tag。保留 [v0.2.0](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.2.0) 及實際備份，依[回復步驟](docs/replies.md#migration-and-rollback)處理。

## 設定與日常使用

整合的「設定」可新增／移除音箱或調整接收方式。`native` 接收官方整合更新；`volume_push` 由對應音箱推送觸發歷史讀取，沒有閒置輪詢與手動試驗視窗。

Marshall Uxbridge 依已記錄的 Uxbridge 查核建議 `volume_push`，首次選取會啟用；這不代表其他實體音箱或接收方式已驗證。未知音箱預設 `native`；未知音箱或覆寫已知設定時，須勾選 **Explicitly allow this unverified speaker / method** 才能啟用。接收開關不能繞過同意。診斷的 `validation_scope` 為 `uxbridge_volume_push` 或 `unverified`。實機範圍由 [驗收報告](docs/hardware-acceptance.md)記錄，不再在每個安裝中寫死 pending 標記。

每個音箱有接收開關、語音事件及診斷感測器，關閉、移除或更改方式只撤銷該音箱舊 session。接收意圖可跨重新啟動保存；關閉後不會自行開啟。帳號/API 重新連線會換新 session，還原的舊事件不會觸發動作。狀態包含 `disabled`、`ready`、`waiting`、`error`、`unsupported`；`ready` 只代表本機準備完成。

相容路徑每次最多兩個請求、每個最多二十秒，共用帳號 worker 並保留來源身分。失敗後等待 30／60／120／240 秒（上限 240 秒），五次連續失敗轉為 `error`；需期限後的新推送才重試，成功空結果亦重設失敗次數。沒有自主歷史重試輪詢。帳號狀態以 HA 通知與每五秒的本機 API 身分檢查觀察。結構不支援或 hook 所有權衝突會停止受影響路徑，保留官方整合；錯誤為固定代碼，不洩漏原始例外。更多狀態與復原細節見 [English README](README.md#current-behavior)。

## 匯入 Blueprint

HA → 設定 → 自動化與場景 → Blueprint → 匯入，貼上：

```text
https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.3.0/blueprints/automation/alexa_voice_events/phrase_to_action.yaml
```

匯入與整合安裝彼此獨立，不會自動建立家庭自動化。從 Blueprint 建立自動化，選音箱的語音事件、每行填一個完整口令，再選 HA 動作。比對會去除首尾空白、合併空白並轉小寫；若實際文字含 `alexa`，口令也要包含。複雜情境用 HA 自動化；官方 Alexa Devices 的播報等動作可直接在 HA 使用。

預設 `queued`、`max: 10`，可在建立後的自動化 YAML 調整。排隊動作執行前重新檢查十五秒內的新鮮度、接收開關與 session；已執行中的任意使用者動作由 HA 管理。切換家庭動作時停用重疊的舊接收者，避免重複執行。

語音文字遵循 HA recorder 政策，無額外歷史資料庫。家庭場景、裝置品牌的家庭規則、碼表量測及音樂恢復均交給 HA。v0.3.0 Blueprint 以固定候選安裝並實測，與正式 tag／HACS 安裝分開記錄；精確版本與限制見[本輪驗收](docs/hardware-simplified-replies.md)；排錯先看接收狀態／錯誤，再到 [issues](https://github.com/vincent97277/ha-alexa-voice-events/issues) 提供版本與重現步驟，遮蔽語音及帳號／裝置識別資訊。

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
