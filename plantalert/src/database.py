"""Gestion de la base de données SQLite pour les périodes froides PlantAlert."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

from configparser import ConfigParser

LOGGER = logging.getLogger(__name__)
def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class ColdPeriodAlert:
    """Représentation d'une période froide continue pour les plantes."""

    alert_id: int
    threshold: float
    start_date: datetime
    end_date: datetime
    min_temp: float
    min_temp_date: datetime
    created_at: datetime
    last_notified_at: Optional[datetime]


@dataclass(slots=True)
class NotificationRecord:
    """Historique d'envoi d'une alerte."""

    notification_id: int
    alert_id: Optional[int]
    message: str
    channels: Sequence[str]
    sent_at: datetime


@dataclass(slots=True)
class ForecastCacheEntry:
    """Entrée de cache des prévisions météo."""

    cache_id: int
    forecast_data: dict
    fetched_at: datetime


class DatabaseManager:
    """Encapsule la gestion des connexions et des opérations SQLite."""

    def __init__(self, db_path: Path, timeout: float = 5.0) -> None:
        self.db_path = db_path
        self.timeout = timeout
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_config(cls, config_path: Path) -> "DatabaseManager":
        parser = ConfigParser()
        parser.read(config_path)

        config_file = Path(config_path).resolve()
        project_root = config_file.parent.parent

        db_path = Path(parser.get("database", "db_path", fallback="data/alerts.db"))
        if not db_path.is_absolute():
            db_path = project_root / db_path

        timeout = parser.getfloat("database", "timeout", fallback=5.0)
        return cls(db_path=db_path, timeout=timeout)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Crée les tables nécessaires pour la détection des périodes froides."""

        LOGGER.debug("Initialisation de la base %s", self.db_path)
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS current_alerts (
                    id INTEGER PRIMARY KEY,
                    threshold REAL NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    min_temp REAL NOT NULL,
                    min_temp_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_notified_at TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_history (
                    id INTEGER PRIMARY KEY,
                    alert_id INTEGER,
                    message TEXT NOT NULL,
                    channels TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    FOREIGN KEY (alert_id) REFERENCES current_alerts (id)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forecast_cache (
                    id INTEGER PRIMARY KEY,
                    forecast_data TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_current_alerts_threshold
                ON current_alerts(threshold, start_date);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_notification_history_alert
                ON notification_history(alert_id, sent_at DESC);
                """
            )

    def get_active_alerts(self, reference_time: Optional[datetime] = None) -> List[ColdPeriodAlert]:
        """Retourne les périodes froides qui se chevauchent avec l'instant donné."""

        if reference_time is None:
            reference_time = datetime.now()
        reference_iso = _to_iso(reference_time)

        query = (
            "SELECT id, threshold, start_date, end_date, min_temp, min_temp_date, created_at, last_notified_at "
            "FROM current_alerts WHERE end_date >= ? ORDER BY start_date ASC"
        )

        with self.connection() as conn:
            rows = conn.execute(query, (reference_iso,)).fetchall()

        alerts: List[ColdPeriodAlert] = []
        for row in rows:
            alerts.append(
                ColdPeriodAlert(
                    alert_id=row["id"],
                    threshold=row["threshold"],
                    start_date=_from_iso(row["start_date"]),
                    end_date=_from_iso(row["end_date"]),
                    min_temp=row["min_temp"],
                    min_temp_date=_from_iso(row["min_temp_date"]),
                    created_at=_from_iso(row["created_at"]),
                    last_notified_at=_from_iso(row["last_notified_at"]) if row["last_notified_at"] else None,
                )
            )
        return alerts

    def save_alert(
        self,
        threshold: float,
        start_date: datetime,
        end_date: datetime,
        min_temp: float,
        min_temp_date: datetime,
        created_at: Optional[datetime] = None,
        last_notified_at: Optional[datetime] = None,
    ) -> int:
        """Insère une nouvelle période froide et retourne son identifiant."""

        created_at = created_at or datetime.now()

        query = (
            "INSERT INTO current_alerts (threshold, start_date, end_date, min_temp, min_temp_date, created_at, last_notified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            threshold,
            _to_iso(start_date),
            _to_iso(end_date),
            float(min_temp),
            _to_iso(min_temp_date),
            _to_iso(created_at),
            _to_iso(last_notified_at) if last_notified_at else None,
        )

        with self.connection() as conn:
            cursor = conn.execute(query, params)
            alert_id = cursor.lastrowid
            LOGGER.info("Période froide enregistrée (id=%s, seuil=%.1f)", alert_id, threshold)
            return int(alert_id)

    def update_last_notified(self, alert_id: int, when: Optional[datetime] = None) -> None:
        """Met à jour la date de dernière notification pour une période froide."""

        when = when or datetime.now()
        with self.connection() as conn:
            conn.execute(
                "UPDATE current_alerts SET last_notified_at = ? WHERE id = ?",
                (_to_iso(when), alert_id),
            )

    def delete_alert(self, alert_id: int) -> None:
        """Supprime une période froide de la base."""

        with self.connection() as conn:
            conn.execute("DELETE FROM current_alerts WHERE id = ?", (alert_id,))

    def record_notification(self, alert_id: Optional[int], message: str, channels: Sequence[str], sent_at: Optional[datetime] = None) -> None:
        """Enregistre l'envoi d'une notification multi-canaux."""

        sent_at = sent_at or datetime.now()
        channel_value = ",".join(channels)
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO notification_history (alert_id, message, channels, sent_at) VALUES (?, ?, ?, ?)",
                (alert_id, message, channel_value, _to_iso(sent_at)),
            )

    def get_notification_history(self, alert_id: int) -> List[NotificationRecord]:
        """Retourne l'historique des notifications associées à une alerte."""

        query = (
            "SELECT id, alert_id, message, channels, sent_at FROM notification_history "
            "WHERE alert_id = ? ORDER BY sent_at DESC"
        )
        with self.connection() as conn:
            rows = conn.execute(query, (alert_id,)).fetchall()

        history: List[NotificationRecord] = []
        for row in rows:
            channels = tuple(filter(None, (row["channels"] or "").split(",")))
            history.append(
                NotificationRecord(
                    notification_id=row["id"],
                    alert_id=row["alert_id"],
                    message=row["message"],
                    channels=channels,
                    sent_at=_from_iso(row["sent_at"]),
                )
            )
        return history

    def upsert_forecast_cache(self, forecast_data: dict, fetched_at: Optional[datetime] = None) -> None:
        """Met à jour le cache des prévisions 48h."""

        fetched_at = fetched_at or datetime.now()
        payload = json.dumps(forecast_data, ensure_ascii=False)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO forecast_cache (id, forecast_data, fetched_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET forecast_data = excluded.forecast_data, fetched_at = excluded.fetched_at
                """,
                (payload, _to_iso(fetched_at)),
            )

    def get_forecast_cache(self) -> Optional[ForecastCacheEntry]:
        """Récupère le cache des prévisions s'il est présent."""

        with self.connection() as conn:
            row = conn.execute(
                "SELECT id, forecast_data, fetched_at FROM forecast_cache ORDER BY fetched_at DESC LIMIT 1"
            ).fetchone()

        if not row:
            return None

        return ForecastCacheEntry(
            cache_id=row["id"],
            forecast_data=json.loads(row["forecast_data"]),
            fetched_at=_from_iso(row["fetched_at"]),
        )


def _main() -> None:  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Outils de maintenance de la base PlantAlert")
    parser.add_argument("command", choices=["init"], help="Commande à exécuter")
    parser.add_argument(
        "--config",
        dest="config",
        default=Path(__file__).resolve().parents[1] / "config" / "settings.ini",
    )
    args = parser.parse_args()

    manager = DatabaseManager.from_config(Path(args.config))
    if args.command == "init":
        manager.init_db()
        print(f"Base de données initialisée dans {manager.db_path}")


if __name__ == "__main__":  # pragma: no cover
    _main()
