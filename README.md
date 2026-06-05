# 運動賽事訂閱行事曆

自動產生 NBA、MLB、F1、世界杯賽程的 `.ics` 訂閱檔，讓 Apple 行事曆自動更新。

支援指定球隊過濾（例如只看湖人、馬刺、道奇等）。資料來源：MLB Stats API、ESPN、Jolpica/Ergast F1 API。

## 一、部署到 GitHub（一次性設定，約 5 分鐘）

### 1. 建立 GitHub Repo

到 https://github.com/new 建立一個 repo（例如叫 `sports-calendar`），**設為 Public**（Apple 行事曆才訂閱得到）。

### 2. 上傳檔案

在這個資料夾打開終端機：

```bash
cd "/Users/chenszu-jung/Library/Application Support/.../outputs/sports-calendar"
git init -b main
git add .
git commit -m "init"
git remote add origin https://github.com/<你的帳號>/sports-calendar.git
git push -u origin main
```

### 3. 啟用 GitHub Actions 寫入權限

Repo → Settings → Actions → General → 最下面 "Workflow permissions" → 選 **Read and write permissions** → Save。

### 4. 手動觸發第一次執行

Repo → Actions 分頁 → 點左邊 "Update Sports Calendar" → 右上 "Run workflow" → 點綠色按鈕。

等 1~2 分鐘跑完，會自動 commit 一個 `docs/sports.ics`。

### 5. 取得訂閱 URL

URL 格式：

```
https://raw.githubusercontent.com/<你的帳號>/sports-calendar/main/docs/sports.ics
```

可以先在瀏覽器打開確認檔案有內容。

## 二、訂閱到 Apple 行事曆

### Mac
1. 打開「行事曆」App
2. 選單列 → 檔案 → 新增行事曆訂閱
3. 貼上上面的 URL → 訂閱
4. 自動更新頻率選 **每天**

### iPhone / iPad
1. 設定 → 行事曆 → 帳號 → 加入帳號 → 其他
2. 加入已訂閱行事曆
3. 伺服器：貼上 URL
4. 完成

加完之後 Apple 行事曆會自動定期重抓檔案。

## 三、修改追蹤球隊

編輯 `config.yaml`，commit 推上去，GitHub Actions 會在下次跑（每天 UTC 16:00 / 台北 00:00）時自動更新。或到 Actions 分頁手動 Run workflow 立即更新。

### NBA / MLB Team ID 對照

| NBA | ID |  | MLB | ID |
|---|---|---|---|---|
| 湖人 Lakers | 13 |  | 道奇 Dodgers | 119 |
| 馬刺 Spurs | 24 |  | 洋基 Yankees | 147 |
| 勇士 Warriors | 9 |  | 太空人 Astros | 117 |
| 塞爾提克 Celtics | 2 |  | 老虎 Tigers | 116 |
| 獨行俠 Mavericks | 6 |  | 教士 Padres | 135 |
| 太陽 Suns | 21 |  | 紅襪 Red Sox | 111 |
| 雷霆 Thunder | 25 |  | 大都會 Mets | 121 |
| 公鹿 Bucks | 15 |  | 勇士 Braves | 144 |
| 76人 76ers | 20 |  | 費城人 Phillies | 143 |
| 金塊 Nuggets | 7 |  | 水手 Mariners | 136 |
| 熱火 Heat | 14 |  | 響尾蛇 D-backs | 109 |

### F1
直接改 `f1.sessions` 區塊，把要看的場次設 `true`。

### 世界杯
直接改 `worldcup.teams`，用英文國名（例如 `Argentina`、`Brazil`）。`knockout_all: true` 會把所有淘汰賽都納入。

## 四、本機測試（可選）

```bash
pip install -r requirements.txt
python generate.py
open docs/sports.ics  # Mac 雙擊也能匯入測試
```

## 目前的設定

- **NBA**：湖人、馬刺
- **MLB**：道奇、洋基、太空人、老虎
- **F1**：排位賽 + 正賽 + Sprint 排位 + Sprint 正賽（不含 FP1/FP2/FP3）
- **世界杯**：阿根廷、巴西、法國、英格蘭、日本、韓國、挪威、葡萄牙、西班牙
- **時區**：行事曆內部存 UTC，Apple 行事曆會自動換成你裝置上的時區（台北 UTC+8）

## 更新頻率

GitHub Actions 每天台北 00:00 自動跑一次。也可以隨時手動 Run workflow。
