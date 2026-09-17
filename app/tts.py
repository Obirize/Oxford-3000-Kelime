"""Telaffuz seslendirme.

Birincil kaynak Google TTS'tir (dogal ses). Indirilen mp3 data/audio/ altinda
onbellege alinir; ayni kelime bir daha internet gerektirmez.
Internet yoksa Windows'un yerlesik SAPI sesine duser.

mp3 calmak icin harici kutuphane kullanilmaz - Windows'un kendi winmm/MCI
arayuzu uzerinden calinir.
"""

from __future__ import annotations

import ctypes
import re
import threading
from pathlib import Path

from . import paths

ROOT = paths.PROJECT_DIR
AUDIO_DIR = paths.data_dir() / "audio"

_SAFE = re.compile(r"[^a-z0-9_-]")
_alias_counter = 0
_lock = threading.Lock()


def _cache_path(word: str) -> Path:
    slug = _SAFE.sub("_", word.lower().strip())
    return AUDIO_DIR / f"{slug}.mp3"


def _download(word: str, path: Path) -> bool:
    try:
        from gtts import gTTS
    except ImportError:
        return False
    try:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        gTTS(word, lang="en", tld="com").save(str(tmp))
        tmp.replace(path)
        return True
    except Exception:
        return False


def _play_mp3(path: Path) -> bool:
    """Windows MCI ile mp3 calar (harici bagimlilik yok)."""
    global _alias_counter
    with _lock:
        _alias_counter += 1
        alias = f"tts{_alias_counter}"
    try:
        winmm = ctypes.windll.winmm
    except AttributeError:
        return False
    buf = ctypes.create_string_buffer(255)

    def send(cmd: str) -> int:
        return winmm.mciSendStringW(cmd, buf, 254, 0)

    if send(f'open "{path}" type mpegvideo alias {alias}') != 0:
        return False
    try:
        send(f"play {alias} wait")
    finally:
        send(f"close {alias}")
    return True


def _speak_sapi(word: str) -> bool:
    """Internet yoksa Windows'un yerlesik sesi."""
    try:
        import win32com.client  # type: ignore
        win32com.client.Dispatch("SAPI.SpVoice").Speak(word)
        return True
    except Exception:
        pass
    try:
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Add-Type -AssemblyName System.Speech; "
             "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
             f".Speak('{word}')"],
            capture_output=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def _speak_blocking(word: str) -> None:
    path = _cache_path(word)
    if not path.exists():
        _download(word, path)
    if path.exists() and _play_mp3(path):
        return
    _speak_sapi(word)


def speak(word: str) -> None:
    """Kelimeyi seslendirir. Arayuzu bloklamamak icin ayri is parcaciginda calisir."""
    if not word.strip():
        return
    threading.Thread(target=_speak_blocking, args=(word,), daemon=True).start()


def is_cached(word: str) -> bool:
    return _cache_path(word).exists()


def prefetch(words: list[str], on_progress=None) -> None:
    """Kelime seslerini arka planda topluca indirir (tamamen cevrimdisi kullanim)."""

    def run():
        total = len(words)
        for i, word in enumerate(words, 1):
            path = _cache_path(word)
            if not path.exists():
                _download(word, path)
            if on_progress and (i % 10 == 0 or i == total):
                on_progress(i, total)

    threading.Thread(target=run, daemon=True).start()


def cache_size() -> tuple[int, float]:
    """(dosya sayisi, toplam MB)"""
    if not AUDIO_DIR.exists():
        return 0, 0.0
    files = list(AUDIO_DIR.glob("*.mp3"))
    return len(files), sum(f.stat().st_size for f in files) / 1_048_576
