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

# 指定字幕語言優先順序，並用 YouTube 自動翻譯成繁體中文
python yt_transcript.py VIDEO_ID --lang en ja --translate zh-Hant

# 一次處理很多支影片（urls.txt 一行一個網址），輸出到 transcripts/ 資料夾
python yt_transcript.py --file urls.txt -o transcripts/

# 先看看這支影片有哪些字幕語言
python yt_transcript.py VIDEO_ID --list-langs
```

支援的網址格式：`watch?v=`、`youtu.be/`、`shorts/`、`embed/`、`live/`、`m.youtube.com`、`music.youtube.com`，或直接給 11 碼影片 ID。

### 小提醒

- 預設語言順序是 繁中 → 簡中 → 英文，人工字幕優先於自動字幕；都沒有的話會拿影片現有的任何字幕。
- 影片本身必須有字幕（包含 YouTube 自動產生的字幕）。作者關閉字幕的影片抓不到。
- YouTube 會擋雲端主機（AWS、GCP 等）的 IP。請在自己的電腦或公司網路執行；真的需要在伺服器上跑，可以加 `--proxy http://user:pass@host:port`。

### 測試

```bash
python -m unittest test_yt_transcript.py
```
