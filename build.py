#!/usr/bin/env python3
"""把 yt_transcript.py 打包成兩個成品，放在 dist/：

- install-termux.sh：Android 手機用的一鍵安裝檔（程式內嵌，不需要另外下載）
- youtube-transcript.skill：Claude Cowork / Claude 桌面版可安裝的技能包

主程式只維護根目錄這一份 yt_transcript.py，改完重跑 `python build.py` 即可。
"""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

INSTALLER_HEAD = """\
#!/data/data/com.termux/files/usr/bin/bash
# YouTube 逐字稿：Termux 一鍵安裝
# 用法：在 Termux 執行  bash install-termux.sh
set -e

echo "【1/4】取得手機儲存空間權限（跳出視窗時請按「允許」）"
if [ ! -d "$HOME/storage/downloads" ]; then
    termux-setup-storage
    for _ in $(seq 1 30); do
        [ -d "$HOME/storage/downloads" ] && break
        sleep 1
    done
fi
if [ ! -d "$HOME/storage/downloads" ]; then
    echo "還沒拿到儲存空間權限，請允許後再執行一次這個安裝檔。"
    exit 1
fi

echo "【2/4】安裝 Python"
pkg install -y python

echo "【3/4】安裝字幕套件"
pip install --upgrade "youtube-transcript-api>=1.2,<2"

echo "【4/4】安裝程式與「分享到 Termux」功能"
mkdir -p "$HOME/yt-transcript" "$HOME/bin"
"""

INSTALLER_TAIL = """\
chmod +x "$HOME/bin/termux-url-opener"

cat > "$HOME/bin/yt" <<'__YT_CMD__'
#!/data/data/com.termux/files/usr/bin/bash
exec python "$HOME/yt-transcript/yt_transcript.py" -o "$HOME/storage/downloads/YouTube逐字稿" "$@"
__YT_CMD__
chmod +x "$HOME/bin/yt"

mkdir -p "$HOME/storage/downloads/YouTube逐字稿"
echo
echo "✅ 安裝完成！"
echo "・在 YouTube App 按「分享」→ 選 Termux，逐字稿會存到「下載/YouTube逐字稿」並自動打開。"
echo "・也可以在 Termux 輸入：yt 影片網址 --timestamps   （進階選項輸入 yt --help 查看）"
"""


def heredoc(target: str, content: str, marker: str) -> str:
    assert f"\n{marker}\n" not in f"\n{content}\n", f"內容裡出現了結束標記 {marker}"
    return f"cat > \"{target}\" <<'{marker}'\n{content.rstrip()}\n{marker}\n"


def build_installer() -> Path:
    script = (ROOT / "yt_transcript.py").read_text(encoding="utf-8")
    opener = (ROOT / "android" / "termux-url-opener").read_text(encoding="utf-8")
    text = (
        INSTALLER_HEAD
        + heredoc("$HOME/yt-transcript/yt_transcript.py", script, "__YT_TRANSCRIPT_PY__")
        + heredoc("$HOME/bin/termux-url-opener", opener, "__TERMUX_URL_OPENER__")
        + INSTALLER_TAIL
    )
    out = DIST / "install-termux.sh"
    out.write_text(text, encoding="utf-8", newline="\n")
    out.chmod(0o755)
    return out


def build_skill() -> Path:
    skill_dir = ROOT / "skill" / "youtube-transcript"
    out = DIST / "youtube-transcript.skill"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(skill_dir / "SKILL.md", "youtube-transcript/SKILL.md")
        zf.write(ROOT / "yt_transcript.py", "youtube-transcript/scripts/yt_transcript.py")
    return out


if __name__ == "__main__":
    DIST.mkdir(exist_ok=True)
    for path in (build_installer(), build_skill()):
        print(f"已產生 {path.relative_to(ROOT)}")
