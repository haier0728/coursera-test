# coursera-test
Coursera test repository

## YouTube 逐字稿下載工具（`yt_transcript.py`）

貼上任何 YouTube 影片網址，就能把字幕存成 `.txt` 逐字稿。

### 安裝

```bash
pip install -r requirements.txt
```

### 使用方式

```bash
# 最基本：存成「影片標題 [影片ID].txt」
python yt_transcript.py https://www.youtube.com/watch?v=VIDEO_ID

# 每行加上時間戳記
python yt_transcript.py https://youtu.be/VIDEO_ID --timestamps

# 原文逐字稿翻譯成繁體中文（YouTube 自動翻譯）
python yt_transcript.py VIDEO_ID --translate zh-Hant

# 指定字幕語言優先順序（不要原文時使用）
python yt_transcript.py VIDEO_ID --lang zh-TW en

# 一次處理很多支影片（urls.txt 一行一個網址），輸出到 transcripts/ 資料夾
python yt_transcript.py --file urls.txt -o transcripts/

# 先看看這支影片有哪些字幕語言
python yt_transcript.py VIDEO_ID --list-langs
```

支援的網址格式：`watch?v=`、`youtu.be/`、`shorts/`、`embed/`、`live/`、`m.youtube.com`、`music.youtube.com`，或直接給 11 碼影片 ID。

### 小提醒

- 預設抓**影片原本講的語言**（原文逐字稿），同語言有人工字幕就優先用人工字幕。想要特定語言用 `--lang`，想看中文用 `--translate zh-Hant`。
- 影片本身必須有字幕（包含 YouTube 自動產生的字幕）。作者關閉字幕的影片抓不到。
- YouTube 會擋雲端主機（AWS、GCP 等）的 IP。請在自己的電腦或公司網路執行；真的需要在伺服器上跑，可以加 `--proxy http://user:pass@host:port`。

### 在手機上使用（Android，不需要電腦）

透過免費 App **Termux**，直接在手機上執行這支程式。手機網路不會被 YouTube 擋。

1. 從 **F-Droid** 安裝 Termux（Google Play 上的版本太舊，不建議）。想要完成時跳出小提示，可以再裝 Termux:API（選用）。
2. 把 `dist/install-termux.sh` 下載到手機的「下載」資料夾。
3. 打開 Termux，依序輸入（第一行會跳出權限視窗，請按「允許」）：
   ```bash
   termux-setup-storage
   bash ~/storage/downloads/install-termux.sh
   ```
4. 完成！之後在 YouTube App 按 **分享 → Termux**，逐字稿就會存到「下載/YouTube逐字稿」並自動打開。
   也可以在 Termux 輸入 `yt 影片網址 --translate zh-Hant` 使用進階選項。

### 用 Claude Cowork 操作電腦（技能包）

把 `dist/youtube-transcript.skill` 安裝到 Claude（設定 → 技能 / Skills → 上傳）。之後在手機上跟 Claude 說「幫我抓這支影片的逐字稿並整理重點 + 網址」，電腦上的 Claude 會執行程式、存檔並回覆摘要。

### 修改程式後重新打包

主程式只有根目錄的 `yt_transcript.py` 一份，改完執行 `python build.py`，就會重新產生 `dist/` 裡的手機安裝檔和技能包。

### 測試

```bash
python -m unittest test_yt_transcript.py
```
