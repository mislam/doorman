"""Environment-backed configuration (worker/.env)."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__version__ = "0.0.0"


class Settings(BaseSettings):
	"""See worker/.env.example for variables."""

	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		extra="ignore",
	)

	stream_url: str = Field(
		default="",
		validation_alias=AliasChoices("STREAM_URL", "RTSP_URL"),
	)
	ha_webhook_url: str = ""
	faces_dir: str = "config/faces"
	gallery_path: str = "config/gallery.pkl"
	recognition_threshold: float = 0.4
	frames_per_event: int = 5
	worker_host: str = "127.0.0.1"
	worker_port: int = 8768
