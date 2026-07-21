# Sports Calendar 訂閱

自動產生 NBA、MLB、F1、世界杯、VNL（世界排球聯賽）賽程的 `.ics` 訂閱檔，讓 Apple 行事曆（或任何支援 ICS 的行事曆）自動同步。

支援指定球隊過濾（例如只看湖人、馬刺、道奇等）；MLB 另外支援「只顯示追蹤球員出賽的場次」。資料來源：MLB Stats API、ESPN、Jolpica/Ergast F1 API。

> 本專案是公開模板，使用者可以 Fork 後自行設定。詳見下方「安全性說明」。

## 功能

- ⚾ MLB：可設定「追蹤球員」，只有這些球員出賽的場次才會出現在行事曆（先發投手／打線命中皆可），不指定球員時則顯示指定球隊全季賽程（含春訓 / 季後賽）
- 🏀 NBA：指定球隊（例行賽 + 季後賽，自動跨季）
- 🏎️ F1：依場次類型過濾（FP1/FP2/FP3/Q/Sprint/Race）
- 🏐 VNL：世界排球聯賽，男排 / 女排各自指定追蹤國家
- ⚽ World Cup 2026：指定國家小組賽 + 可選全部淘汰賽
- 時間自動轉成你的時區（預設台北 UTC+8）
- GitHub Actions 每 3 小時自動更新一次

## 安全性說明

- 本專案**不使用任何 API key 或機密資料**，所有資料源都是公開 API
- Repo 必須設為 **Public**，因為 Apple 行事曆訂閱需要可公開存取的 URL
- Repo 中**不會出現任何個人識別資料**，公開 repo 只有：球隊清單（你選的）、產生的 `.ics`（含公開賽程資料）、產生程式
- Workflow 只有 `contents: write` 權限，且只能對自己的 repo 寫入（GITHUB_TOKEN 自動範圍）
- 你訂閱的 ICS URL 只有你知道，但如果連結被分享，看到的人也只是知道你追蹤哪些球隊（沒有更敏感的內容）

如果不想公開球隊清單，可改用以下替代方案：
1. 改成 private repo + 啟用 GitHub Pages 並設定授權，這樣會比較複雜
2. 改用 Cron + 私人 hosting（Cloudflare Workers / Vercel 等）

## 快速開始（給 Fork 的人）

### 1. Fork 這個 repo
點右上角 **Fork** → 設為 **Public**。

### 2. 編輯 `config.yaml`
打開 `config.yaml`，把球隊改成你要追蹤的：

```yaml
nba:
  enabled: true
  teams:
    - { id: 13, name: "Los Angeles Lakers", zh: "湖人" }

mlb:
  enabled: true
  teams:
    - { id: 119, name: "Los Angeles Dodgers", zh: "道奇" }
  # 選填：只追蹤特定球員出賽的場次（不設定就顯示 teams 全部賽程）
  # track: "pitcher"（先發投手）/ "lineup"（打線，賽前數小時才有）/ "both"（兩刀流）
  tracked_players:
    - { id: 660271, zh: "大谷翔平", track: "both" }

f1:
  enabled: true
  season: 2026
  sessions:
    qualifying: true
    race: true
    sprint_qualifying: true
    sprint: true

vnl:
  enabled: true
  season: 2026
  teams:
    men:
      - "Japan"
    women:
      - "Japan"
      - "Brazil"

worldcup:
  enabled: true
  teams:
    - "Japan"
    - "Argentina"
  knockout_all: false
```

球隊 ID 對照見下方表格。

> ⚠️ **設定 `tracked_players` 時要注意**：`teams` 是抓資料的範圍，追蹤球員所屬的球隊一定要在 `teams` 清單裡，不然系統根本不會去抓他的比賽，永遠偵測不到他出賽。

### 3. 啟用 Actions 寫入權限
Repo → **Settings** → **Actions** → **General** → 最下面 **Workflow permissions** → 選 **Read and write permissions** → **Save**。

> 這個權限只允許 workflow commit 到你自己這個 repo，不會影響其他地方。

### 4. 觸發第一次執行
Repo → **Actions** 分頁 → 左邊 **Update Sports Calendar** → 右上 **Run workflow** → 點綠色按鈕。

等 1~2 分鐘跑完，會自動 commit `docs/sports.ics`。

### 5. 訂閱

URL 格式（把 `<USER>` 換成你的 GitHub 帳號）：

```
https://raw.githubusercontent.com/<USER>/sports-calendar/main/docs/sports.ics
```

**iPhone / iPad：** 設定 → 行事曆 → 帳號 → 加入帳號 → 其他 → 加入已訂閱行事曆 → 貼上 URL。

**Mac：** 行事曆 App → 檔案 → 新增行事曆訂閱 → 貼 URL → 自動更新選每天。

**Google Calendar：** 設定 → 加入行事曆 → 從網址加入 → 貼 URL。

## Team ID 對照表

### NBA（ESPN team ID）

| ID | 中文 | 英文 |  | ID | 中文 | 英文 |
|---|---|---|---|---|---|---|
| 1 | 老鷹 | Hawks |  | 16 | 灰狼 | Timberwolves |
| 2 | 塞爾提克 | Celtics |  | 17 | 籃網 | Nets |
| 3 | 鵜鶘 | Pelicans |  | 18 | 尼克 | Knicks |
| 4 | 公牛 | Bulls |  | 19 | 魔術 | Magic |
| 5 | 騎士 | Cavaliers |  | 20 | 76人 | 76ers |
| 6 | 獨行俠 | Mavericks |  | 21 | 太陽 | Suns |
| 7 | 金塊 | Nuggets |  | 22 | 拓荒者 | Trail Blazers |
| 8 | 活塞 | Pistons |  | 23 | 國王 | Kings |
| 9 | 勇士 | Warriors |  | 24 | 馬刺 | Spurs |
| 10 | 火箭 | Rockets |  | 25 | 雷霆 | Thunder |
| 11 | 溜馬 | Pacers |  | 26 | 爵士 | Jazz |
| 12 | 快艇 | Clippers |  | 27 | 巫師 | Wizards |
| 13 | 湖人 | Lakers |  | 28 | 暴龍 | Raptors |
| 14 | 熱火 | Heat |  | 29 | 灰熊 | Grizzlies |
| 15 | 公鹿 | Bucks |  | 30 | 黃蜂 | Hornets |

### MLB（MLB Stats API team ID）

| ID | 中文 | 英文 |  | ID | 中文 | 英文 |
|---|---|---|---|---|---|---|
| 108 | 天使 | Angels |  | 134 | 海盜 | Pirates |
| 109 | 響尾蛇 | D-backs |  | 135 | 教士 | Padres |
| 110 | 金鶯 | Orioles |  | 136 | 水手 | Mariners |
| 111 | 紅襪 | Red Sox |  | 137 | 巨人 | Giants |
| 112 | 小熊 | Cubs |  | 138 | 紅雀 | Cardinals |
| 113 | 紅人 | Reds |  | 139 | 光芒 | Rays |
| 114 | 守護者 | Guardians |  | 140 | 遊騎兵 | Rangers |
| 115 | 落磯 | Rockies |  | 141 | 藍鳥 | Blue Jays |
| 116 | 老虎 | Tigers |  | 142 | 雙城 | Twins |
| 117 | 太空人 | Astros |  | 143 | 費城人 | Phillies |
| 118 | 皇家 | Royals |  | 144 | 勇士 | Braves |
| 119 | 道奇 | Dodgers |  | 145 | 白襪 | White Sox |
| 120 | 國民 | Nationals |  | 146 | 馬林魚 | Marlins |
| 121 | 大都會 | Mets |  | 147 | 洋基 | Yankees |
| 133 | 運動家 | Athletics |  | 158 | 釀酒人 | Brewers |

### F1
直接改 `f1.sessions` 區塊：把要看的場次設 `true`。

### 世界杯
用英文國名（例如 `Japan`、`Argentina`、`Brazil`）。設 `knockout_all: true` 會把所有淘汰賽都納入（不限定隊伍）。

## 本機測試（可選）

```bash
pip install -r requirements.txt
python generate.py
```

會在 `docs/sports.ics` 產生檔案，雙擊可在 Mac 行事曆預覽。

## 排程

預設每 3 小時自動跑一次（`cron: "0 */3 * * *"`）。之所以比「每天一次」密，是為了接住 MLB 打線名單（賽前 2~3 小時才公布）這種時效較短的資料——如果只追蹤先發投手，其實每天一次就夠了。修改 `.github/workflows/update-calendar.yml` 的 cron 可調整頻率。

## 監控與通知（可選）

Workflow 內建：
- **事件數驗證**：產出 `.ics` 如果 < 100 筆，自動視為失敗（防止 ESPN 暫時掛掉但 workflow 卻成功）
- **Telegram 推送**：失敗時即時通知；成功且 `.ics` 有實際變動時才推播（避免每 3 小時跑一次卻洗版「檢查完成、無異動」的訊息）

### 啟用 Telegram 通知

1. **建立 Bot**：Telegram 搜 `@BotFather` → `/newbot` → 取名 → 拿到 token（類似 `7123456789:AAH8z...`）
2. **找 Chat ID**：搜你剛建的 bot → 按 Start → 對它說 `/start`
3. 瀏覽器打開 `https://api.telegram.org/bot<你的TOKEN>/getUpdates`，找 `"chat":{"id":XXXXX}` 那個數字
4. **加 GitHub Secrets**：Repo → Settings → Secrets and variables → Actions → New repository secret，加兩個：
   - `TELEGRAM_BOT_TOKEN` = bot token
   - `TELEGRAM_CHAT_ID` = chat ID

設定完之後不用改 workflow，下次跑就會通知。Secrets 是加密儲存，公開 repo 也安全。

如果沒設這兩個 secret，workflow 一樣會跑，只是不會推 Telegram。

### GitHub 預設通知

Workflow 失敗時 GitHub 預設會寄 email 到你的帳號 email（前提是 Settings → Notifications 把 Actions 那欄打勾）。

## VNL Finals 對戰自動同步

VNL（世界排球聯賽）決賽週期（8 強～冠軍賽）的對手要等前一輪打完才知道，`data/vnl_{season}.yaml` 沒辦法像小組賽一樣提前整理好，以前只能人工盯著 Wikipedia 手動補。`vnl_finals_sync.py` 會在賽事日期窗口內自動讀該屆賽事 Wikipedia 頁面的 wikitext（比渲染後的網頁更新更快、格式更穩定），解析已確定對手的場次，補進 `data/vnl_{season}.yaml`，讓既有每 3 小時一次的排程自動接手（重新產生 `.ics` → commit → TG 通知），不用另外開 workflow。

- **只在窗口內動作**：日期窗口寫在 `vnl_finals_sync.py` 的 `FINALS_EVENTS`，非賽事期間完全不會發 HTTP 請求
- **防呆**：抓到的隊伍代碼如果不在賽前就已知的 8 強名單內，視為異常直接跳過、記警告，不會誤寫進行事曆
- **失敗保護**：Wikipedia 抓取或解析失敗只記警告、不中斷整個 workflow（NBA/MLB/F1 等其他賽事照常執行）
- **每年要手動更新一次**：VNL 每年主辦城市、場館、晉級隊伍都不同，`FINALS_EVENTS`（日期窗口、場館名、8 強名單）需要在每年 Finals 開打前手動改一次——跟 `data/vnl_2026.yaml` 本身一樣，是有意設計成部分手動維護的

## HYROX 開賣監控（獨立模組）

`hyrox/monitor.py` + `.github/workflows/hyrox-monitor.yml`：監控 HYROX 場次官網，開放報名的瞬間發 Telegram 通知（含可直接點的購票按鈕）。與上面的行事曆功能互相獨立，共用同一組 Telegram secrets。

- **判斷方式**：雙訊號——官網「Ticket sales start soon!」字樣消失 + 購票連結出現，兩者都成立才判定開賣
- **三級通知**：🔥 開賣（附購票連結）／⏰ 頁面異動（可能公告了開賣時間，之後 72 小時內升頻為每 5 分鐘緊盯）／⚠️ 監控失靈（連續抓取失敗，大聲求救而不是默默躺平）
- **節流**：排程每 5 分鐘喚醒，平常自我節流成 30 分鐘實際檢查一次
- **新增場次**：在 `hyrox/monitor.py` 的 `TARGETS` 清單加一筆（id、名稱、場次頁網址、官網網域）即可，判斷與通知邏輯自動套用
- **本機測試**：`python3 hyrox/monitor.py --selftest`（用開賣中場次驗證判斷函式）、`--dry-run`（檢查但不發訊息）、`--test`（發 3 則樣本訊息驗格式）

## 授權

MIT License。詳見 [LICENSE](LICENSE)。

## 資料來源

- MLB Stats API：https://statsapi.mlb.com
- ESPN NBA / World Cup：https://site.api.espn.com
- F1：https://api.jolpi.ca （Ergast 後繼）
- VNL：小組賽整理自 Wikipedia（見 `data/vnl_{season}.yaml` 檔頭註解）；Finals 對戰由 `vnl_finals_sync.py` 自動讀 Wikipedia wikitext

所有資料源皆為公開 API，本專案不附帶任何賠率 / 博弈資訊。
