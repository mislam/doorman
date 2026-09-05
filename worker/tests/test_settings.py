from settings import Settings


def test_settings_defaults() -> None:
	settings = Settings(_env_file=None)
	assert settings.faces_dir == "config/faces"
	assert settings.gallery_path == "config/gallery.pkl"
	assert settings.recognition_threshold == 0.4
	assert settings.frames_per_event == 5
	assert settings.worker_port == 8768
