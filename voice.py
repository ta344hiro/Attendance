import subprocess
import tempfile

# === OpenJTalk 設定 ===
OPENJTALK_DIC = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
VOICE = "/usr/share/hts-voice/mei/mei_normal.htsvoice"

def speak_jp(text: str) -> None:
    """日本語音声を再生"""
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        subprocess.run(
            ["open_jtalk", "-x", OPENJTALK_DIC, "-m", VOICE, "-ow", f.name],
            input=text.encode("utf-8"),
            check=True,
        )
        subprocess.run(["aplay", f.name], check=True)