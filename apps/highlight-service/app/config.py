from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_text_model: str = "gpt-5.5"
    openai_image_model: str = "gpt-image-2"
    openai_wire_api: str = "responses"
    openai_transcribe_model: str = "whisper-1"
    transcribe_provider: str = "gemini"
    gemini_api_key: str = ""
    google_gemini_base_url: str = ""
    gemini_base_url: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    gemini_tts_voice: str = "Kore"
    gemini_api_style: str = "native"
    video_input_dir: str = "inputs"
    max_workers: int = 2
    baidu_pcs_go_path: str = "/Users/q/Desktop/work/baidupcs-go/BaiduPCS-Go-v4.0.1-darwin-osx-amd64/BaiduPCS-Go"
    baidu_pcs_remote_root: str = "/短剧资源"
    baidu_pcs_timeout_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    @property
    def input_dir(self) -> Path:
        path = Path(self.video_input_dir)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    @property
    def output_dir(self) -> Path:
        return BASE_DIR / "outputs" / "highlights"

    @property
    def promo_dir(self) -> Path:
        return BASE_DIR / "outputs" / "promos"

    @property
    def data_dir(self) -> Path:
        return BASE_DIR / "data"

    @property
    def work_dir(self) -> Path:
        return BASE_DIR / "work"

    @property
    def reports_dir(self) -> Path:
        return BASE_DIR / "outputs" / "reports"

    @property
    def intro_template_asset_dir(self) -> Path:
        return BASE_DIR / "work" / "intro-template-assets"

    @property
    def workflow_dir(self) -> Path:
        return BASE_DIR / "outputs" / "workflows"


@lru_cache
def get_settings() -> Settings:
    return Settings()
