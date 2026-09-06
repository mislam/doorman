"""POST recognition results to Home Assistant notify webhook."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 10.0


def notify_ha(
	webhook_url: str,
	payload: dict[str, object],
	*,
	timeout: float = DEFAULT_TIMEOUT_S,
) -> bool:
	"""POST *payload* to the HA webhook. Returns True when a notify was sent."""
	if not webhook_url:
		logger.info("HA_WEBHOOK_URL not set — skipping notify")
		return False

	try:
		response = requests.post(webhook_url, json=payload, timeout=timeout)
		response.raise_for_status()
	except requests.RequestException:
		logger.exception("HA notify failed")
		return False

	logger.info("HA notify sent (%s)", response.status_code)
	return True
