# Alexa Voice Events

[English](README.md)

將 Alexa 語音事件交給 Home Assistant 自動化處理。選擇官方 Alexa Devices 已登入的帳號與音箱，再用 Blueprint 或 HA 自動化設定口令與動作。

## 開發狀態與支援版本

目前為公開**開發版**。多帳號、多音箱、接收設定與故障恢復已實作並通過軟體測試；manifest 的 `0.1.0` 是預定首版，**尚無正式 tag／release**。新版 Uxbridge／Blueprint 實機驗收待完成，舊整合的測試不代表新版已通過；其他音箱須明確同意試用，仍屬未驗證。

需要 **HA Core 2026.10.1**、官方 **Alexa Devices** 與 **aioamazondevices 16.3.2**。先完成官方整合登入。本整合重用其 API，不要求另一組憑證，也不開第二條連線。其他版本須經重新審查與測試；不要為本整合降級 Core。

## 安裝

選擇一種方式：

- **手動：**下載專案，僅將 `custom_components/alexa_voice_events` 複製到 HA 設定目錄的 `custom_components/` 下（通常是 `/config/custom_components/alexa_voice_events`），重新啟動 HA。
- **HACS 自訂儲存庫：**HACS → ⋮ → 自訂儲存庫，新增 `https://github.com/vincent97277/ha-alexa-voice-events`，類別選 **Integration**，下載 Alexa Voice Events，再重新啟動 HA。本專案未加入 HACS 預設商店；首個 release 前會安裝預設分支，內容會隨開發更新。

在 HA → 設定 → 裝置與服務 → 新增整合，選 **Alexa Voice Events**，選取既有 Alexa Devices 帳號與音箱。每個帳號最多一個項目，可選多個音箱；其他帳號另加項目，不能跨帳號選音箱。

可重現的軟體測試基準為 [`4944eea`](https://github.com/vincent97277/ha-alexa-voice-events/tree/4944eeabc51e4735d189c8db4a51ea31a65aca44)。它的執行程式與 Blueprint 和本次發佈相同，HACS metadata、CI 與雙語說明在其後加入。需要固定該執行版本時，手動下載該 revision；另記安裝 commit，不能只看 manifest 版本。正式實機驗收後才會建立相互對應的整合與 Blueprint 版本標籤。

## 設定與日常使用

整合的「設定」可新增／移除音箱或調整接收方式。`native` 接收官方整合更新；`volume_push` 由對應音箱推送觸發歷史讀取，沒有閒置輪詢與手動試驗視窗。

Marshall Uxbridge 依**舊版證據**建議 `volume_push`，首次選取會啟用，但新版實機驗收仍待完成。未知音箱預設 `native`；未知音箱或覆寫已知設定時，須勾選 **Explicitly allow this unverified speaker / method** 才能啟用。接收開關不能繞過同意。診斷的 `validation_scope` 為 `legacy_uxbridge` 或 `unverified`，`new_hardware_acceptance` 仍為 `pending`。

每個音箱有接收開關、語音事件及診斷感測器，關閉、移除或更改方式只撤銷該音箱舊 session。接收意圖可跨重新啟動保存；關閉後不會自行開啟。帳號/API 重新連線會換新 session，還原的舊事件不會觸發動作。狀態包含 `disabled`、`ready`、`waiting`、`error`、`unsupported`；`ready` 只代表本機準備完成。

相容路徑每次最多兩個請求、每個最多二十秒，共用帳號 worker 並保留來源身分。失敗後等待 30／60／120／240 秒（上限 240 秒），五次連續失敗轉為 `error`；需期限後的新推送才重試，成功空結果亦重設失敗次數。沒有自主歷史重試輪詢。帳號狀態以 HA 通知與每五秒的本機 API 身分檢查觀察。結構不支援或 hook 所有權衝突會停止受影響路徑，保留官方整合；錯誤為固定代碼，不洩漏原始例外。更多狀態與復原細節見 [English README](README.md#current-behavior)。

## 匯入 Blueprint

HA → 設定 → 自動化與場景 → Blueprint → 匯入，貼上：

```text
https://github.com/vincent97277/ha-alexa-voice-events/blob/4944eeabc51e4735d189c8db4a51ea31a65aca44/blueprints/automation/alexa_voice_events/phrase_to_action.yaml
```

匯入與整合安裝彼此獨立，不會自動建立家庭自動化。從 Blueprint 建立自動化，選音箱的語音事件、每行填一個完整口令，再選 HA 動作。比對會去除首尾空白、合併空白並轉小寫；若實際文字含 `alexa`，口令也要包含。複雜情境用 HA 自動化；官方 Alexa Devices 的播報等動作可直接在 HA 使用。

預設 `queued`、`max: 10`，可在建立後的自動化 YAML 調整。排隊動作執行前重新檢查十五秒內的新鮮度、接收開關與 session；已執行中的任意使用者動作由 HA 管理。切換家庭動作時停用重疊的舊接收者，避免重複執行。

語音文字遵循 HA recorder 政策，無額外歷史資料庫。家庭場景、裝置品牌的家庭規則、碼表量測及音樂恢復均交給 HA。本開發版尚未安裝到家庭 HA；排錯先看接收狀態／錯誤，再到 [issues](https://github.com/vincent97277/ha-alexa-voice-events/issues) 提供版本與重現步驟，遮蔽語音及帳號／裝置識別資訊。

## 開發與授權

測試環境：Python **3.14.5**、HA **2026.10.1**、pytest-homeassistant-custom-component **0.13.372**、aioamazondevices **16.3.2**；精確相依版本記於 `uv.lock`。

```sh
uv sync --locked
uv run pytest
uv run mypy
uv run ruff check .
uv run ruff format --check .
```

測試使用真實 HA 設定、實體生命週期與自動化／Blueprint 引擎，以及上游 coordinator／dispatcher／parser；只控制遠端回應與時鐘，禁用外部 socket，使用合成資料。這證明軟體行為，不代表 Amazon 傳遞、實體動作或其他音箱已驗證。CI 另以 hassfest 與 HACS action 驗證封裝；HACS 的品牌商店檢查不適用自訂儲存庫，因此略過 `brands`。

[Apache-2.0](LICENSE)，來源與第三方歸屬見 [NOTICE](NOTICE)。測試執行安裝的相依套件，未散佈上游 parser 摘錄或家庭錄音。相容邏輯由原本本機實作重構，已移除家庭依賴。
