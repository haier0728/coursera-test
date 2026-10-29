#!/usr/bin/env python3
"""YouTube 逐字稿下載工具：輸入任何 YouTube 影片網址或 ID，輸出逐字稿 .txt 檔。

用法範例：
    python yt_transcript.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
    python yt_transcript.py https://youtu.be/dQw4w9WgXcQ --timestamps
    python yt_transcript.py VIDEO_ID --translate zh-Hant
    python yt_transcript.py VIDEO_ID --lang zh-TW en
    python yt_transcript.py --file urls.txt -o transcripts/
    python yt_transcript.py VIDEO_ID --list-langs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)
from youtube_transcript_api.proxies import GenericProxyConfig


# 兩句之間停頓超過這麼多秒，就另起一段（僅在不加時間戳記時使用）
PARAGRAPH_GAP_SECONDS = 2.0
PARAGRAPH_MAX_CHARS = 600

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿가-힯＀-￯]")


class TranscriptError(Exception):
    """可預期、要以友善訊息呈現給使用者的錯誤。"""


@dataclass
class Snippet:
    text: str
    start: float
    duration: float


@dataclass
class TranscriptResult:
    video_id: str
    title: Optional[str]
    language: str
    language_code: str
    is_generated: bool
    translated_to: Optional[str]
    snippets: list[Snippet]


def extract_video_id(value: str) -> str:
    """從各種 YouTube 網址格式（或直接的 ID）取出 11 碼影片 ID。"""
    value = value.strip()
    if _VIDEO_ID_RE.match(value):
        return value

    if "://" not in value:
        value = "https://" + value
    parsed = urllib.parse.urlparse(value)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path_parts = [p for p in parsed.path.split("/") if p]

    candidate = None
    if host == "youtu.be" and path_parts:
        candidate = path_parts[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        query = urllib.parse.parse_qs(parsed.query)
        if "v" in query:
            candidate = query["v"][0]
        elif len(path_parts) >= 2 and path_parts[0] in ("shorts", "embed", "live", "v", "e"):
            candidate = path_parts[1]

    if candidate and _VIDEO_ID_RE.match(candidate):
        return candidate
    raise TranscriptError(f"看不出這是哪支 YouTube 影片：{value}")


def fetch_title(video_id: str) -> Optional[str]:
    """透過 oEmbed 取得影片標題；拿不到就回傳 None，不影響主流程。"""
    url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.load(resp).get("title")
    except Exception:
        return None


def make_api(proxy: Optional[str]) -> YouTubeTranscriptApi:
    if proxy:
        return YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy))
    return YouTubeTranscriptApi()


def _base_lang(code: str) -> str:
    return code.split("-")[0].lower()


def _pick_original(available):
    """挑影片原本講的語言。YouTube 的自動字幕是語音辨識產生的，它的語言就是影片的原文；
    同語言有人工字幕就優先用人工字幕（比較準）。沒有自動字幕時，拿第一個人工字幕。"""
    generated = [t for t in available if t.is_generated]
    if not generated:
        return available[0]
    spoken = _base_lang(generated[0].language_code)
    for t in available:
        if not t.is_generated and _base_lang(t.language_code) == spoken:
            return t
    return generated[0]


def _pick_transcript(transcript_list, langs: Optional[list[str]]):
    """沒指定語言時抓原文字幕；有指定時依優先順序找（人工 > 自動），都沒有就退回原文。"""
    available = list(transcript_list)
    if not available:
        raise TranscriptError("這支影片沒有任何字幕（包含自動字幕）。")
    if not langs:
        return _pick_original(available)
    try:
        return transcript_list.find_manually_created_transcript(langs)
    except NoTranscriptFound:
        pass
    try:
        return transcript_list.find_generated_transcript(langs)
    except NoTranscriptFound:
        pass
    return _pick_original(available)


def get_transcript(
    video_id: str,
    langs: Optional[list[str]] = None,
    translate_to: Optional[str] = None,
    api: Optional[YouTubeTranscriptApi] = None,
) -> TranscriptResult:
    api = api or YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
        transcript = _pick_transcript(transcript_list, langs)
        translated_to = None
        if translate_to and transcript.language_code != translate_to:
            if not transcript.is_translatable:
                raise TranscriptError(f"這支影片的字幕不支援翻譯成 {translate_to}")
            transcript = transcript.translate(translate_to)
            translated_to = translate_to
        fetched = transcript.fetch()
    except TranscriptError:
        raise
    except TranscriptsDisabled:
        raise TranscriptError("這支影片的作者關閉了字幕功能，抓不到逐字稿。")
    except VideoUnavailable:
        raise TranscriptError("影片不存在、已下架或設為私人。")
    except NoTranscriptFound:
        raise TranscriptError("這支影片沒有任何字幕（包含自動字幕）。")
    except YouTubeTranscriptApiException as exc:
        first_line = str(exc).strip().splitlines()
        if type(exc).__name__ in ("IpBlocked", "RequestBlocked"):
            raise TranscriptError(
                "YouTube 擋下了這個網路位址的請求（雲端主機 IP 常被擋）。"
                "請在一般家用 / 公司網路執行，或用 --proxy 指定代理伺服器。"
            )
        raise TranscriptError(f"抓取逐字稿失敗：{type(exc).__name__} {first_line[0] if first_line else ''}")

    snippets = [
        Snippet(text=" ".join(s.text.split()), start=s.start, duration=s.duration)
        for s in fetched
        if s.text and s.text.strip()
    ]
    return TranscriptResult(
        video_id=video_id,
        title=None,
        language=transcript.language,
        language_code=transcript.language_code,
        is_generated=transcript.is_generated,
        translated_to=translated_to,
        snippets=snippets,
    )


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _join(a: str, b: str) -> str:
    """中日韓文字之間不加空白，其他語言用空白銜接。"""
    if not a:
        return b
    if _CJK_RE.match(a[-1]) or _CJK_RE.match(b[0]):
        return a + b
    return a + " " + b


def to_paragraphs(snippets: Iterable[Snippet]) -> list[str]:
    paragraphs: list[str] = []
    current = ""
    prev_end: Optional[float] = None
    for s in snippets:
        gap = s.start - prev_end if prev_end is not None else 0.0
        if current and (gap >= PARAGRAPH_GAP_SECONDS or len(current) >= PARAGRAPH_MAX_CHARS):
            paragraphs.append(current)
            current = ""
        current = _join(current, s.text)
        prev_end = s.start + s.duration
    if current:
        paragraphs.append(current)
    return paragraphs


def render_text(result: TranscriptResult, timestamps: bool = False, header: bool = True) -> str:
    lines: list[str] = []
    if header:
        kind = "自動產生字幕" if result.is_generated else "人工字幕"
        lang = f"{result.language} ({result.language_code})"
        if result.translated_to:
            lang += f"，已翻譯為 {result.translated_to}"
        lines += [
            f"標題：{result.title or '(未取得)'}",
            f"網址：https://www.youtube.com/watch?v={result.video_id}",
            f"字幕：{lang}・{kind}",
            "",
            "-" * 40,
            "",
        ]
    if timestamps:
        lines += [f"[{format_timestamp(s.start)}] {s.text}" for s in result.snippets]
    else:
        lines.append("\n\n".join(to_paragraphs(result.snippets)))
    return "\n".join(lines).rstrip() + "\n"


def safe_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name[:max_len] or "transcript"


def output_path(result: TranscriptResult, out_dir: Path) -> Path:
    base = f"{safe_filename(result.title)} [{result.video_id}]" if result.title else result.video_id
    return out_dir / f"{base}.txt"


def list_languages(video_id: str, api: YouTubeTranscriptApi) -> None:
    transcript_list = api.list(video_id)
    print(f"影片 {video_id} 可用的字幕：")
    for t in transcript_list:
        kind = "自動" if t.is_generated else "人工"
        trans = "，可翻譯" if t.is_translatable else ""
        print(f"  {t.language_code:<10} {t.language}（{kind}{trans}）")


def read_inputs(args: argparse.Namespace) -> list[str]:
    inputs = list(args.videos)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                inputs.append(line)
    return inputs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="把任何 YouTube 影片的字幕下載成逐字稿 .txt 檔。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("\n\n", 1)[1],
    )
    p.add_argument("videos", nargs="*", help="YouTube 網址或 11 碼影片 ID，可一次給多個")
    p.add_argument("-f", "--file", help="從文字檔讀取網址清單（一行一個，# 開頭為註解）")
    p.add_argument("-o", "--output-dir", default=".", help="輸出資料夾（預設為目前資料夾）")
    p.add_argument(
        "-l", "--lang", nargs="+",
        help="指定字幕語言優先順序，例如 --lang zh-TW en（預設：抓影片原本講的語言，也就是原文逐字稿）",
    )
    p.add_argument("-t", "--translate", metavar="LANG", help="用 YouTube 自動翻譯成指定語言，例如 zh-Hant")
    p.add_argument("--timestamps", action="store_true", help="每行前面加上時間戳記 [mm:ss]")
    p.add_argument("--no-header", action="store_true", help="不要在檔案開頭加標題 / 網址等資訊")
    p.add_argument("--stdout", action="store_true", help="直接印在畫面上，不存檔")
    p.add_argument("--list-langs", action="store_true", help="只列出影片有哪些字幕語言")
    p.add_argument("--proxy", help="代理伺服器，例如 http://user:pass@host:port")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = read_inputs(args)
    if not inputs:
        build_parser().print_help()
        return 2

    api = make_api(args.proxy)
    out_dir = Path(args.output_dir)
    failures = 0

    for raw in inputs:
        try:
            video_id = extract_video_id(raw)
            if args.list_langs:
                list_languages(video_id, api)
                continue
            result = get_transcript(video_id, args.lang, args.translate, api)
            result.title = fetch_title(video_id)
            text = render_text(result, timestamps=args.timestamps, header=not args.no_header)
            if args.stdout:
                sys.stdout.write(text)
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            path = output_path(result, out_dir)
            path.write_text(text, encoding="utf-8")
            print(f"✅ {result.title or video_id} → {path}")
        except (TranscriptError, YouTubeTranscriptApiException) as exc:
            failures += 1
            print(f"❌ {raw}：{exc}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
