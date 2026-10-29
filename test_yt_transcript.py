"""yt_transcript.py 的離線測試：用假的字幕物件模擬 YouTube，不需要連網。

執行：python -m unittest test_yt_transcript.py
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

import yt_transcript as yt


class FakeTranscript:
    def __init__(self, code, generated, snippets, translatable=True):
        self.language_code = code
        self.language = {"en": "English", "zh-TW": "中文（台灣）", "ja": "Japanese"}.get(code, code)
        self.is_generated = generated
        self.is_translatable = translatable
        self._snippets = snippets

    def fetch(self):
        return [SimpleNamespace(text=t, start=s, duration=d) for t, s, d in self._snippets]

    def translate(self, code):
        return FakeTranscript(code, self.is_generated, [(f"[{code}] {t}", s, d) for t, s, d in self._snippets])


class FakeTranscriptList:
    def __init__(self, transcripts):
        self._transcripts = transcripts

    def __iter__(self):
        return iter(self._transcripts)

    def _find(self, langs, generated):
        for code in langs:
            for t in self._transcripts:
                if t.language_code == code and t.is_generated == generated:
                    return t
        raise NoTranscriptFound("abcdefghijk", langs, self)

    def find_manually_created_transcript(self, langs):
        return self._find(langs, False)

    def find_generated_transcript(self, langs):
        return self._find(langs, True)


def fake_api(transcripts=None, error=None):
    api = mock.Mock()
    if error:
        api.list.side_effect = error
    else:
        api.list.return_value = FakeTranscriptList(transcripts)
    return api


EN_SNIPPETS = [("Hello  everyone,", 0.0, 1.5), ("welcome\nback.", 1.5, 1.5), ("New topic.", 6.0, 2.0)]
CLEAN_SNIPPETS = [("Hello everyone,", 0.0, 1.5), ("welcome back.", 1.5, 1.5), ("New topic.", 6.0, 2.0)]


class ExtractVideoIdTest(unittest.TestCase):
    def test_supported_formats(self):
        vid = "dQw4w9WgXcQ"
        for url in [
            vid,
            f"https://www.youtube.com/watch?v={vid}",
            f"https://youtube.com/watch?feature=share&v={vid}&t=42s",
            f"https://m.youtube.com/watch?v={vid}",
            f"https://music.youtube.com/watch?v={vid}&list=RD",
            f"https://youtu.be/{vid}?si=abc",
            f"youtu.be/{vid}",
            f"https://www.youtube.com/shorts/{vid}",
            f"https://www.youtube.com/embed/{vid}",
            f"https://www.youtube.com/live/{vid}?feature=share",
            f"https://www.youtube-nocookie.com/embed/{vid}",
        ]:
            with self.subTest(url=url):
                self.assertEqual(yt.extract_video_id(url), vid)

    def test_invalid(self):
        for bad in ["", "hello", "https://vimeo.com/123456", "https://www.youtube.com/channel/UC123"]:
            with self.subTest(bad=bad), self.assertRaises(yt.TranscriptError):
                yt.extract_video_id(bad)


class GetTranscriptTest(unittest.TestCase):
    def test_prefers_manual_in_language_order(self):
        api = fake_api([
            FakeTranscript("en", True, EN_SNIPPETS),
            FakeTranscript("en", False, EN_SNIPPETS),
            FakeTranscript("zh-TW", False, [("大家好", 0, 1)]),
        ])
        result = yt.get_transcript("abcdefghijk", ["zh-TW", "en"], api=api)
        self.assertEqual(result.language_code, "zh-TW")
        self.assertFalse(result.is_generated)

    def test_default_picks_original_language(self):
        # 日文影片：自動字幕是日文，另外有人工英文字幕 → 預設應抓日文
        api = fake_api([
            FakeTranscript("en", False, EN_SNIPPETS),
            FakeTranscript("ja", True, [("こんにちは", 0, 1)]),
        ])
        result = yt.get_transcript("abcdefghijk", api=api)
        self.assertEqual(result.language_code, "ja")

        # 同語言有人工字幕時優先用人工字幕
        api = fake_api([
            FakeTranscript("en", False, EN_SNIPPETS),
            FakeTranscript("ja", True, [("こんにちは", 0, 1)]),
            FakeTranscript("ja-JP", False, [("こんにちは。", 0, 1)]),
        ])
        result = yt.get_transcript("abcdefghijk", api=api)
        self.assertEqual((result.language_code, result.is_generated), ("ja-JP", False))

        # 完全沒有自動字幕時拿第一個人工字幕
        api = fake_api([FakeTranscript("en", False, EN_SNIPPETS)])
        self.assertEqual(yt.get_transcript("abcdefghijk", api=api).language_code, "en")

    def test_falls_back_to_generated_then_original(self):
        api = fake_api([FakeTranscript("en", True, EN_SNIPPETS)])
        self.assertTrue(yt.get_transcript("abcdefghijk", ["en"], api=api).is_generated)

        api = fake_api([FakeTranscript("ja", True, [("こんにちは", 0, 1)])])
        self.assertEqual(yt.get_transcript("abcdefghijk", ["zh-TW", "en"], api=api).language_code, "ja")

    def test_translate(self):
        api = fake_api([FakeTranscript("en", False, EN_SNIPPETS)])
        result = yt.get_transcript("abcdefghijk", ["en"], translate_to="zh-Hant", api=api)
        self.assertEqual(result.translated_to, "zh-Hant")
        self.assertTrue(result.snippets[0].text.startswith("[zh-Hant]"))

    def test_translate_not_supported(self):
        api = fake_api([FakeTranscript("en", False, EN_SNIPPETS, translatable=False)])
        with self.assertRaisesRegex(yt.TranscriptError, "不支援翻譯"):
            yt.get_transcript("abcdefghijk", ["en"], translate_to="zh-Hant", api=api)

    def test_no_transcripts(self):
        with self.assertRaisesRegex(yt.TranscriptError, "沒有任何字幕"):
            yt.get_transcript("abcdefghijk", ["en"], api=fake_api([]))

    def test_disabled(self):
        api = fake_api(error=TranscriptsDisabled("abcdefghijk"))
        with self.assertRaisesRegex(yt.TranscriptError, "關閉了字幕"):
            yt.get_transcript("abcdefghijk", ["en"], api=api)

    def test_whitespace_normalised(self):
        api = fake_api([FakeTranscript("en", False, EN_SNIPPETS + [("   ", 9, 1)])])
        result = yt.get_transcript("abcdefghijk", ["en"], api=api)
        self.assertEqual([s.text for s in result.snippets], ["Hello everyone,", "welcome back.", "New topic."])


class RenderTest(unittest.TestCase):
    def make_result(self, snippets, title="My Video"):
        return yt.TranscriptResult(
            video_id="abcdefghijk", title=title, language="English", language_code="en",
            is_generated=False, translated_to=None,
            snippets=[yt.Snippet(t, s, d) for t, s, d in snippets],
        )

    def test_paragraphs_split_on_pause(self):
        text = yt.render_text(self.make_result(CLEAN_SNIPPETS), header=False)
        self.assertEqual(text, "Hello everyone, welcome back.\n\nNew topic.\n")

    def test_cjk_joined_without_spaces(self):
        text = yt.render_text(self.make_result([("大家好", 0, 1), ("歡迎回來", 1, 1)]), header=False)
        self.assertEqual(text, "大家好歡迎回來\n")

    def test_timestamps(self):
        snippets = [("Intro", 5, 1), ("Later", 3725, 1)]
        text = yt.render_text(self.make_result(snippets), timestamps=True, header=False)
        self.assertEqual(text, "[00:05] Intro\n[01:02:05] Later\n")

    def test_header(self):
        text = yt.render_text(self.make_result(CLEAN_SNIPPETS))
        self.assertIn("標題：My Video", text)
        self.assertIn("https://www.youtube.com/watch?v=abcdefghijk", text)
        self.assertIn("人工字幕", text)

    def test_output_path(self):
        out = Path("out")
        self.assertEqual(yt.output_path(self.make_result([], 'A/B: "C"?'), out), out / "A_B_ _C__ [abcdefghijk].txt")
        self.assertEqual(yt.output_path(self.make_result([], None), out), out / "abcdefghijk.txt")


class MainTest(unittest.TestCase):
    def test_writes_file_and_reports_failures(self):
        api = fake_api([FakeTranscript("en", False, EN_SNIPPETS)])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(yt, "make_api", return_value=api), \
                mock.patch.object(yt, "fetch_title", return_value="Demo"), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            code = yt.main(["https://youtu.be/abcdefghijk", "https://vimeo.com/123", "-o", tmp])
            self.assertEqual(code, 1)  # 有一個失敗
            written = Path(tmp) / "Demo [abcdefghijk].txt"
            self.assertTrue(written.exists())
            self.assertIn("Hello everyone, welcome back.", written.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
