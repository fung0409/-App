# 記帳 App — 部署說明

## 專案結構

```
finance-app/
├── app.py              # Flask 後端主程式
├── requirements.txt    # Python 套件清單
├── Procfile            # Render 啟動指令
├── .gitignore
├── templates/
│   ├── index.html      # 主頁面（記帳月曆）
│   └── login.html      # 登入 / 註冊頁
└── static/
    └── manifest.json   # PWA 設定
```

---

## 第一步：在本機測試

```bash
# 1. 進入專案資料夾
cd finance-app

# 2. 建立虛擬環境
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. 安裝套件
pip install -r requirements.txt

# 4. 啟動（本機用 SQLite，不需要設定資料庫）
python app.py
```

打開瀏覽器輸入 http://localhost:5000 即可看到 App。

---

## 第二步：推上 GitHub

```bash
git init
git add .
git commit -m "first commit"

# 在 github.com 建立新 repo（不要勾選 README）
# 然後：
git remote add origin https://github.com/你的帳號/finance-app.git
git push -u origin main
```

---

## 第三步：部署到 Render（免費）

1. 前往 https://render.com → 用 GitHub 帳號登入
2. 點「New +」→「Web Service」
3. 選擇你的 finance-app repo → 點 Connect
4. 填入以下設定：
   - Name: finance-app（隨意）
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT`
5. 點「Add Environment Variable」新增：
   - `SECRET_KEY` → 隨機字串（例如：abc123xyz456，越長越好）
6. 點「Create Web Service」→ 等待 2-3 分鐘部署完成

### 加入免費 PostgreSQL 資料庫：
1. 在 Render Dashboard 點「New +」→「PostgreSQL」
2. 選 Free 方案 → 建立
3. 建立後點進去，複製「Internal Database URL」
4. 回到 Web Service → Environment → 新增：
   - `DATABASE_URL` → 貼上剛才複製的 URL

---

## 第四步：設定 LINE Bot（月底推播）

1. 前往 https://developers.line.biz → 登入
2. 點「Create a new provider」→ 建立
3. 點「Create a Messaging API channel」
4. 填寫資料 → 建立完成後進入 Channel
5. 在「Messaging API」頁籤：
   - 點「Issue」發行 Channel access token（長期）→ 複製
6. 用 LINE App 掃描頁面上的 QR Code 加好友
7. 前往 https://developers.line.biz/console/ → 點你的 Channel
   → 在「Basic settings」找到「Your user ID」→ 複製
8. 回到 Render → Environment 新增：
   - `LINE_CHANNEL_ACCESS_TOKEN` → 貼上步驟 5 的 token
   - `LINE_USER_ID` → 貼上步驟 7 的 User ID

設定完成後，每月最後一天晚上 8 點會自動收到當月財務摘要。

---

## 環境變數一覽

| 變數名稱 | 說明 | 必填 |
|---|---|---|
| `SECRET_KEY` | Session 加密金鑰 | 是 |
| `DATABASE_URL` | PostgreSQL 連線字串 | 是（線上） |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Bot Token | 否（不設則不推播） |
| `LINE_USER_ID` | 你的 LINE User ID | 否（不設則不推播） |

---

## 常見問題

**Q: 部署後打開是錯誤頁？**
→ 在 Render → Logs 查看錯誤訊息，最常見是忘記設定 `SECRET_KEY`。

**Q: 資料庫連線失敗？**
→ 確認 `DATABASE_URL` 開頭是 `postgresql://`（不是 `postgres://`）。
   Render 給的 URL 開頭可能是 `postgres://`，需要手動改成 `postgresql://`。

**Q: 手機要怎麼安裝成 App？**
→ 用手機瀏覽器打開網址 → 點瀏覽器選單 → 「加入主畫面」即可當 App 使用。
