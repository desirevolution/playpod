from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database: str = "data/playpod.sqlite3"
    mpd_host: str = ""
    mpd_port: int = 6600
    mpd_password: str = ""
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    mqtt_topic: str = "podplayer/status"
    tts_timeout_seconds: float = 10
    tts_audio_url: str = ""
    tts_playback_timeout_seconds: float = 120
    refresh_seconds: int = 3600
    static_dir: str = str(Path(__file__).parent.parent / "frontend" / "dist")
    media_base_url: str = ""
    media_roots: str = "{}"
    media_stable_seconds: int = 5
    download_directory: str = ""
    download_max_bytes: int = 2 * 1024**3

    ytdlp_enabled: bool = True
    ytdlp_timeout: int = 3600

    @classmethod
    def from_env(cls):
        return cls(
            database=os.getenv("SQLITE_PATH", "data/playpod.sqlite3"),
            mpd_host=os.getenv("MPD_HOST", "").strip(),
            mpd_port=int(os.getenv("MPD_PORT", "6600")),
            mpd_password=os.getenv("MPD_PASSWORD", ""),
            mqtt_host=os.getenv("MQTT_HOST", ""),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            mqtt_user=os.getenv("MQTT_USER", ""),
            mqtt_password=os.getenv("MQTT_PASSWORD", ""),
            mqtt_topic=os.getenv("MQTT_TOPIC", "podplayer/status"),
            tts_audio_url=os.getenv("TTS_AUDIO_URL", ""),
            tts_playback_timeout_seconds=max(1, float(os.getenv("TTS_PLAYBACK_TIMEOUT_SECONDS", "120"))),
            tts_timeout_seconds=max(.1, min(20, float(os.getenv("TTS_TIMEOUT_SECONDS", "10")))),
            refresh_seconds=max(60, int(os.getenv("RSS_INTERVAL_SECONDS", "3600"))),
            static_dir=os.getenv("STATIC_DIR", cls.static_dir),
            media_base_url=os.getenv("MEDIA_BASE_URL", ""),
            media_roots=os.getenv("MEDIA_ROOTS") or "{}",
            media_stable_seconds=max(0, int(os.getenv("MEDIA_STABLE_SECONDS", "5"))),
            ytdlp_enabled=os.getenv("YTDLP_ENABLED", "true").lower() in ("true", "1", "yes"),
            ytdlp_timeout=max(1, int(os.getenv("YTDLP_TIMEOUT", "3600"))),
            download_directory=os.getenv("DOWNLOAD_DIRECTORY", ""),
            download_max_bytes=max(1, int(os.getenv("DOWNLOAD_MAX_BYTES", str(2 * 1024**3)))),
        )
