<p align="center"><img src="custom_components/alexa_voice_events/brand/icon.png" alt="Alexa Voice Events 圖示" width="160"></p>

# Alexa Voice Events

[English](README.md)

將 Alexa 聽到的文字交給 Home Assistant 執行動作，也能在原發話音箱播報 HA 資訊。
重用既有 **Alexa Devices** 帳號，不必再次登入 Amazon、建立 Custom Skill 或另存語音歷史。

**Alexa 辨識 → 語音事件 → 你的 HA 自動化 → 可選的語音回覆。**
家庭規則留在 HA。本專案是社群整合，並非 Amazon 或 Home Assistant 官方整合。

[安裝](#安裝) · [設定](#設定) · [Blueprint](#blueprint) · [口令建議](#recognized-phrases) · [FAQ](#faq) · [更新與回復](#更新與回復)

## 使用前提

- **Home Assistant Core 2026.10.2**，已設定並登入官方 **Alexa Devices**，其 client 為 **aioamazondevices 16.3.2**。
- 帳號下的音箱。Marshall Uxbridge 有[限定實機證據](docs/hardware-simplified-replies.md)，其他音箱或接收方式需明確同意使用未驗證設定。
- 其他 Core／client 組合須另經查核與測試，不要為此降級 Core。見[相容性](docs/compatibility.md)。

## 安裝

選一種方式，完成後重新啟動 HA：

| 方式 | 步驟 |
| --- | --- |
| HACS 自訂儲存庫 | HACS → ⋮ → 自訂儲存庫 → 加入 `https://github.com/vincent97277/ha-alexa-voice-events`，類別 **Integration** → 下載 Alexa Voice Events **v0.3.1**。本專案未加入預設商店。 |
| 手動 | 下載 [v0.3.1 source ZIP](https://github.com/vincent97277/ha-alexa-voice-events/archive/refs/tags/v0.3.1.zip)，只將 `custom_components/alexa_voice_events`（含 `brand`）放入 HA 設定目錄的 `custom_components/`，通常是 `/config/custom_components/alexa_voice_events`。 |

## 設定

1. 開啟 **設定 → 裝置與服務 → 新增整合 → Alexa Voice Events**。
2. 選擇既有 Alexa Devices 帳號與一個或多個音箱。一個帳號一個 AVE 項目，其他帳號另加項目。
3. 在整合「設定」檢查接收方式。Uxbridge 建議 `volume_push`；未知音箱預設 `native`，啟用前須勾選 **Explicitly allow this unverified speaker / method**。覆寫已知型號建議方式也需要此同意。
4. 音箱原有 HA 裝置下會增加語音事件、接收開關與診斷感測器。`ready` 只表示本機就緒；關接收會阻止新的受管理動作，重開不補播舊口令。

`native` 觀察官方整合更新，`volume_push` 依音箱推送觸發歷史查詢，沒有閒置時持續輪詢歷史。細節見[接收架構](docs/architecture.md)。

## Blueprint

先安裝整合，再到 **設定 → 自動化與場景 → Blueprint → 匯入**，貼上固定版本 URL：

```text
https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.3.1/blueprints/automation/alexa_voice_events/phrase_to_action.yaml
```

[檢視／下載 Blueprint](https://github.com/vincent97277/ha-alexa-voice-events/blob/v0.3.1/blueprints/automation/alexa_voice_events/phrase_to_action.yaml)。
從它建立自動化，設定以下六個欄位。安裝／匯入本身不會自動建立家庭自動化；欄位旁的 **Help** 連到同版英文說明，英文頁首可切到繁中。

### Speakers' voice event entities

選一個或多個 **Alexa Voice Events 的 event 實體**，不是 media player。
回覆固定以一般 **Speak 送到本次發話音箱**，不需序號或回覆模式設定。

### Recognized phrases

**每行一個口令，不加開頭的 `alexa`。** 實際發話仍使用音箱喚醒詞，設定口令時省略即可。

可優先嘗試以下範例，再接到你自己的動作或感測器：

```text
turn the bedroom lights on
turn the bedroom lights off
tell me the bedroom temperature
```

不同動作各建自動化。以上是建議範例，不是內建功能，也不保證辨識結果。

比對忽略大小寫、重複空白及兩側**開頭一次、獨立一字的 `alexa`**。
原本含前綴的設定也能繼續用，不必再寫兩行。原始事件 `voice_command` 保留供排錯。
前綴須以空白分隔；`Alexa, ...` 的逗號不會因此被移除。

其餘仍是字面比對，包含標點、拼寫及後綴。建議先用無標點口令，再核對實際逐字稿。
例如 `light on, please` 只有在辨識文字也含逗號時才匹配，與 `light on please` 不同。
不自動把 bridge 改成 fridge，不刪句中的 Alexa，不處理其他喚醒詞，也不猜語意。

**辨識建議。** 本案例 fridge 曾被辨識成 bridge。完整且相關的語境可能幫助辨識，
例如用 `where is the fridge` 取代單字 `fridge`、用 `turn the bedroom lights on` 取代 `light on`。
這不保證長句更準或 Alexa 一定會糾正發音，加入贅詞也未必有用；在 HA 填口令不會訓練 Alexa。
[依據與排錯](docs/recognized-phrases.md)。

**可選實驗：never mind。** 可自行測試句尾加上 `never mind`，例如
`turn the bedroom lights on never mind`，嘗試減少原生互動。若採用，將實際完整逐字稿（含後綴）填入口令。
它也可能被當成取消、改變逐字稿或沒有預期效果，不能保證既避開原生回答又保留 HA 指令。
另說一句取消也不能假設尚未執行的工作會繼續。[Amazon CancelIntent 文件](https://developer.amazon.com/en-US/docs/alexa/custom-skills/standard-built-in-intents.html)
說明的是 Custom Skill 的取消意圖，不足以證明本方案句尾技巧必定有效。

### Attempt to interrupt the native reply

**預設開啟。** 口令匹配且授權有效時，在 Actions 前嘗試停止發話音箱；**也可能停止音樂**，不需要時可關閉。

此整合觀察辨識後的歷史，並未透過 [Custom Skill 互動模型](https://developer.amazon.com/en-US/alexa/alexa-skills-kit/get-deeper/custom-skills)接管對話，
因此 Alexa 仍可能原生回答或追問。推送／歷史可用性、HA 處理及網路會造成延遲，中止可能要數秒，
不是固定或至少三秒，也沒有成功保證。Stop 動作返回不代表對話已結束。

### Sensors to report

選感測器（例如溫度與濕度），**Reply message 留空**，內建模板就會在 Actions 後產生回答：

> Home Assistant reports: Room temperature is 22.1 °C; Room humidity is 43 %.

沿用 HA 目前記錄的名稱、數值與單位；名稱可為中文，報告句型為英文。
不自動翻譯名稱、換單位、調精度或宣稱剛剛採樣。缺值與無效量測明說 unavailable，不當作零；真正的零有效。
一般文字感測器可照讀文字。自訂格式使用 Reply message。

### Reply message

可填固定文字或 HA 模板。**非空自訂訊息優先於 Sensors to report**；兩欄可同時設定，但只使用自訂訊息。
要完全不播報，同時清空兩欄；Stop 仍獨立控制。

- 固定文字：`The fridge is in the kitchen.`
- 模板：`Home Assistant reports {{ states('sensor.example_value') }}.`

將範例實體換成自己的。一般讀值優先使用感測器選擇，它已處理缺值；需要數值格式時參考
[有驗證的量測模板](docs/replies.md#adapt-a-sensor-query-without-changing-the-integration)，不要把缺值轉成零。
可先在 HA 模板編輯器預覽。資料在 Actions 完成後讀取，而非固定在觸發當下。

### Actions

選擇一般 HA 動作，例如開燈或執行腳本；只查感測值時可留空。
請求順序是 **嘗試停止來源音箱 → 家庭 Actions → 可選的來源音箱 Speak**。

避免多個自動化使用重疊口令，包含省略 Alexa 後相同的口令。同一自動化內多行匹配仍只執行一次；不同自動化仍各自執行。
每步前重新確認接收、session、事件及十五秒期限；同音箱的新事件取代待執行舊工作。
已開始的 Actions 及送往 Amazon 的命令不能撤回。[詳細行為](docs/replies.md)。

## 更新與回復

元件與 Blueprint 維持**同一固定版本**。**HACS 不會更新已匯入的 Blueprint**。
先備份實際元件、Blueprint 內容／路徑及所有消費者設定／啟用狀態；替換、驗證後逐個啟用。

v0.3.1 相容原有含前綴口令，可在核對跨自動化重疊後刪除多餘變體。
`reply_device`／`reply_mode` 在 v0.3.0 已移除，依賴它們的消費者需先調整。
回復時同步還原原檔及完整設定；[v0.3.0](https://github.com/vincent97277/ha-alexa-voice-events/releases/tag/v0.3.0) 保留。
[完整遷移／回復](docs/replies.md#migration-and-rollback)。

## FAQ

**這會取代 Alexa 或改善辨識器嗎？** 不會。Amazon 仍負責辨識及可能的原生互動，AVE 將文字交給 HA 規則。

**沒動作先看哪裡？** 先看接收診斷，再核對新事件的 `voice_command`／來源時間及自動化 trace。
沒有新事件本身不代表 Amazon 沒有逐字稿，見[口令排錯](docs/recognized-phrases.md)。

**可以回到另一台音箱嗎？** 隨附 Blueprint 固定來源 Speak；進階路由可自行組合一般 HA actions 及[目標查詢 API](docs/replies.md#read-only-target-lookup-for-ordinary-ha-automations)。

**排隊的每句都會執行嗎？** 不會。過期、被新事件取代或撤權的工作會退出。
`queued` 是單一自動化的佇列，並非跨自動化音箱鎖。需要時可在自動化 YAML 改 `mode`／`max`，預設 queued／10。

## 隱私、開發與授權

語音事件含辨識文字，依 HA recorder 政策保存，沒有額外歷史資料庫。
[回報問題](https://github.com/vincent97277/ha-alexa-voice-events/issues)時遮蔽語音、憑證與帳號／裝置識別資訊。

[架構](docs/architecture.md) · [開發／測試](docs/development.md) · [版本說明](docs/releases/v0.3.1.md) · [實機範圍](docs/hardware-simplified-replies.md)

[Apache-2.0](LICENSE) · [第三方說明與圖示來源](NOTICE)
