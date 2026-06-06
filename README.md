# Sports Calendar 訂閱

自動產生 NBA、MLB、F1、世界杯賽程的 `.ics` 訂閱檔，讓 Apple 行事曆（或任何支援 ICS 的行事曆）自動同步。

支援指定球隊過濾（例如只看湖人、馬刺、道奇等）。資料來源：MLB Stats API、ESPN、Jolpica/Ergast F1 API。

> 本專案是公開模板，使用者可以 Fork 後自行設定。詳見下方「安全性說明」。

## 功能

- ⚾ MLB：指定球隊全季賽程（含春訓 / 季後賽）
- 🏀 NBA：指定球隊（例行賽 + 季後賽，自動跨季）
- 🏎️ F1：依場次類型過濾（FP1/FP2/FP3/Q/Sprint/Race）
- ⚽ World Cup 2026：指定國家小組賽 + 可選全部淘汰賽
- 時間自動轉成你的時區（預設台北 UTC+8）
- GitHub Actions 每天自動更新

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

f1:
  enabled: true
  season: 2026
  sessions:
    qualifying: true
    race: true
    sprint_qualifying: true
    sprint: true

worldcup:
  enabled: true
  teams:
    - "Japan"
    - "Argentina"
  knockout_all: false
```

球隊 ID 對照見下方表格。

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

預設每天 UTC 16:00（台北 00:00）自動跑。修改 `.github/workflows/update-calendar.yml` 的 cron 可調整。

## 授權

MIT License。詳見 [LICENSE](LICENSE)。

## 資料來源

- MLB Stats API：https://statsapi.mlb.com
- ESPN NBA / World Cup：https://site.api.espn.com
- F1：https://api.jolpi.ca （Ergast 後繼）

所有資料源皆為公開 API，本專案不附帶任何賠率 / 博弈資訊。
