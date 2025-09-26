"""Client Meteo-France spécialisé pour la protection des plantes."""

from __future__ import annotations

import logging
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Sequence

from meteofrance_api.client import MeteoFranceClient
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class HourlyTemperature:
    """Prévision horaire adaptée à la détection de périodes froides."""

    timestamp_utc: datetime
    timestamp_local: datetime
    temperature_c: float
    below_vigilance: bool
    below_freeze: bool


class MeteoFranceWeatherClient:
    """Client Meteo-France pour récupérer les prévisions 48h de Collonges-au-Mont-d'Or."""

    def __init__(
        self,
        city: str,
        timezone_name: str = "Europe/Paris",
        vigilance_threshold: float = 3.0,
        freeze_threshold: float = 0.0,
        forecast_hours: int = 48,
        client: Optional[MeteoFranceClient] = None,
    ) -> None:
        self.city = city
        self.timezone = ZoneInfo(timezone_name)
        self.vigilance_threshold = vigilance_threshold
        self.freeze_threshold = freeze_threshold
        self.forecast_hours = forecast_hours
        self._client = client or MeteoFranceClient()
        self._place: Optional[dict] = None

    @classmethod
    def from_config(cls, config_path: Path | str) -> "MeteoFranceWeatherClient":
        parser = ConfigParser()
        parser.read(config_path)

        city = parser.get("location", "city", fallback="Collonges-au-Mont-d'Or")
        timezone_name = parser.get("location", "timezone", fallback="Europe/Paris")
        vigilance = parser.getfloat("thresholds", "vigilance", fallback=3.0)
        freeze = parser.getfloat("thresholds", "freeze", fallback=0.0)
        forecast_hours = parser.getint("timing", "forecast_hours", fallback=48)

        return cls(
            city=city,
            timezone_name=timezone_name,
            vigilance_threshold=vigilance,
            freeze_threshold=freeze,
            forecast_hours=forecast_hours,
        )

    def _resolve_place(self) -> dict:
        if self._place is not None:
            return self._place

        LOGGER.debug("Recherche de la localisation Meteo-France pour %s", self.city)
        places: Sequence[dict] = self._client.search_places(self.city)
        if not places:
            raise RuntimeError(f"Localisation introuvable pour {self.city}")

        self._place = places[0]
        return self._place

    def get_forecast_48h(self) -> List[HourlyTemperature]:
        """Retourne la prévision horaire utile pour la détection de périodes froides."""

        place = self._resolve_place()
        LOGGER.debug("Récupération des prévisions pour %s", place.get("name", self.city))
        forecast = self._client.get_forecast_for_place(place)
        hourly_entries = getattr(forecast, "forecast", [])

        now_utc = datetime.now(tz=UTC)
        horizon = now_utc + timedelta(hours=self.forecast_hours)

        results: List[HourlyTemperature] = []
        for entry in hourly_entries:
            timestamp = entry.get("dt") or entry.get("time")
            temperature_obj = entry.get("T")
            if isinstance(temperature_obj, dict):
                temperature = temperature_obj.get("value")
            else:
                temperature = temperature_obj

            if timestamp is None or temperature is None:
                continue

            dt_utc = datetime.fromtimestamp(int(timestamp), tz=UTC)
            if dt_utc > horizon:
                break

            dt_local = dt_utc.astimezone(self.timezone)
            temp_value = float(temperature)
            results.append(
                HourlyTemperature(
                    timestamp_utc=dt_utc,
                    timestamp_local=dt_local,
                    temperature_c=temp_value,
                    below_vigilance=temp_value <= self.vigilance_threshold,
                    below_freeze=temp_value <= self.freeze_threshold,
                )
            )

        LOGGER.info("Prévisions froides collectées pour %d heures", len(results))
        return results


__all__ = ["HourlyTemperature", "MeteoFranceWeatherClient"]
