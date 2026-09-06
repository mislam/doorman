"""Environment-backed configuration (worker/.env)."""

from pathlib import Path

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
	stream_user: str = Field(
		default="",
		validation_alias=AliasChoices("STREAM_USER", "RTSP_USER"),
	)
	stream_password: str = Field(
		default="",
		validation_alias=AliasChoices("STREAM_PASSWORD", "RTSP_PASSWORD"),
	)
	ha_webhook_url: str = ""
	db_dir: str = "db"
	recognition_threshold: float = 0.4
	frame_enhance: str = "clahe"
	frames_per_event: int = 5
	worker_host: str = "127.0.0.1"
	worker_port: int = 8768
	enroll_secret: str = ""

	def db_path(self) -> Path:
		return Path(self.db_dir)

	def gallery_path(self) -> Path:
		return self.db_path() / "gallery.pkl"

	def capture_stream_url(self) -> str:
		"""Video URL for OpenCV — injects STREAM_USER/PASSWORD with runtime URL encoding."""
		from stream import build_stream_url

		return build_stream_url(self.stream_url, self.stream_user, self.stream_password)
