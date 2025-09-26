"""Gestion des notifications PlantAlert."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

import requests

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class NotificationMessage:
    """Structure standardisée d'un message d'alerte."""

    title: str
    description: str
    severity: str
    timestamp: datetime

    def to_discord_payload(self, mention_roles: Optional[Iterable[str]] = None) -> dict:
        mentions = " ".join(f"<@&{role}>" for role in mention_roles or [])
        embed = {
            "title": self.title,
            "description": f"{mentions}\n{self.description}".strip(),
            "timestamp": self.timestamp.isoformat(),
            "color": _severity_to_color(self.severity),
        }
        return {"embeds": [embed]}

    def to_notify_send_args(self) -> List[str]:
        return [
            "notify-send",
            f"PlantAlert :: {self.severity.upper()}",
            f"{self.title}\n{self.description}",
        ]


def _severity_to_color(severity: str) -> int:
    mapping = {
        "info": 0x1E90FF,
        "warning": 0xFFA500,
        "watch": 0xFFD700,
        "orange": 0xFF8C00,
        "red": 0xFF0000,
        "critical": 0x8B0000,
    }
    return mapping.get(severity.lower(), 0x2E8B57)


def send_discord_webhook(url: str, message: NotificationMessage, mention_roles: Optional[Iterable[str]] = None) -> bool:
    """Envoie un message formaté vers un webhook Discord."""

    payload = message.to_discord_payload(mention_roles)
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.error("Erreur lors de l'envoi du webhook Discord: %s", exc)
        return False

    LOGGER.info("Notification Discord envoyée (status %s)", response.status_code)
    return True


def send_notify_send(message: NotificationMessage) -> bool:
    """Envoie une notification desktop via notify-send si disponible."""

    if not shutil.which("notify-send"):
        LOGGER.warning("notify-send introuvable sur ce système")
        return False

    try:
        subprocess.run(message.to_notify_send_args(), check=True)
    except subprocess.CalledProcessError as exc:
        LOGGER.error("Erreur notify-send: %s", exc)
        return False

    LOGGER.info("Notification locale envoyée")
    return True


def format_plant_alert_message(
    threshold: float,
    start_date: datetime,
    end_date: datetime,
    min_temp: float,
) -> NotificationMessage:
    """Formate un message d'alerte pour les plantes."""

    if threshold <= 0:
        title = "🥶 ALERTE PLANTES - Gel"
        severity = "critical"
    else:
        title = "🌡️ ALERTE PLANTES - Vigilance 3°C"
        severity = "warning"

    description = (
        "📅 Période froide prévue : "
        f"{start_date.strftime('%d/%m %Hh')} → {end_date.strftime('%d/%m %Hh')}\n"
        f"🥶 Température mini : {min_temp:.1f}°C\n"
        "➡️ Rentrer les plantes sensibles avant ce soir"
    )

    return NotificationMessage(
        title=title,
        description=description,
        severity=severity,
        timestamp=datetime.now(),
    )


__all__ = [
    "NotificationMessage",
    "send_discord_webhook",
    "send_notify_send",
    "format_plant_alert_message",
]
