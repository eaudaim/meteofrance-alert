"""Logique métier des alertes PlantAlert."""

from __future__ import annotations

import logging
from configparser import ConfigParser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .database import ColdPeriodAlert, DatabaseManager
from .notifications import NotificationMessage, format_plant_alert_message
from .weather import HourlyTemperature, MeteoFranceWeatherClient

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ColdPeriod:
    """Période continue pendant laquelle la température reste sous un seuil."""

    threshold: float
    start_date: datetime
    end_date: datetime
    min_temp: float
    min_temp_date: datetime

    @property
    def duration_hours(self) -> float:
        return max(0.0, (self.end_date - self.start_date).total_seconds() / 3600.0)


@dataclass(slots=True)
class AlertAction:
    """Action à réaliser sur une alerte existante ou nouvelle."""

    action_type: str  # "CREATE", "UPDATE", "DELETE", "IGNORE"
    period: ColdPeriod
    existing_alert_id: Optional[int]
    notification_reason: str
    previous_period: Optional[ColdPeriod] = None
    previous_alert: Optional[ColdPeriodAlert] = None
    hours_shortened: Optional[float] = None
    hours_extended: Optional[float] = None


@dataclass(slots=True)
class NotificationData:
    """Conteneur prêt pour l'envoi multi-canaux."""

    action: AlertAction
    message: NotificationMessage
    channels: Sequence[str] = field(default_factory=lambda: ("discord", "notify"))


_THRESHOLD_MAPPING: List[Tuple[str, float]] = [
    ("below_vigilance", 3.0),
    ("below_freeze", 0.0),
]


def configure_thresholds(vigilance: float, freeze: float) -> None:
    """Met à jour les seuils utilisés pour la détection des périodes froides."""

    global _THRESHOLD_MAPPING
    _THRESHOLD_MAPPING = [
        ("below_vigilance", float(vigilance)),
        ("below_freeze", float(freeze)),
    ]


def detect_cold_periods(forecast: List[HourlyTemperature]) -> List[ColdPeriod]:
    """Détecte les périodes froides continues pour chaque seuil configuré."""

    if not forecast:
        return []

    sorted_forecast = sorted(forecast, key=lambda item: item.timestamp_local)
    periods: List[ColdPeriod] = []

    for attribute, threshold in _THRESHOLD_MAPPING:
        current_start: Optional[datetime] = None
        current_end: Optional[datetime] = None
        current_min_temp: Optional[float] = None
        current_min_date: Optional[datetime] = None

        for entry in sorted_forecast:
            is_cold = bool(getattr(entry, attribute, False))
            if is_cold:
                if current_start is None:
                    current_start = entry.timestamp_local
                    current_end = entry.timestamp_local
                    current_min_temp = entry.temperature_c
                    current_min_date = entry.timestamp_local
                else:
                    current_end = entry.timestamp_local
                    if entry.temperature_c < float(current_min_temp):
                        current_min_temp = entry.temperature_c
                        current_min_date = entry.timestamp_local
            elif current_start is not None:
                periods.append(
                    ColdPeriod(
                        threshold=threshold,
                        start_date=current_start,
                        end_date=current_end or current_start,
                        min_temp=float(current_min_temp),
                        min_temp_date=current_min_date or current_start,
                    )
                )
                current_start = None
                current_end = None
                current_min_temp = None
                current_min_date = None

        if current_start is not None:
            periods.append(
                ColdPeriod(
                    threshold=threshold,
                    start_date=current_start,
                    end_date=current_end or current_start,
                    min_temp=float(current_min_temp),
                    min_temp_date=current_min_date or current_start,
                )
            )

    periods.sort(key=lambda period: (period.threshold, period.start_date))
    return periods


def compare_periods(new_periods: List[ColdPeriod], existing_alerts: List[ColdPeriodAlert]) -> List[AlertAction]:
    """Compare les périodes détectées aux alertes enregistrées."""

    actions: List[AlertAction] = []
    existing_by_threshold: Dict[float, List[ColdPeriodAlert]] = {}
    for alert in existing_alerts:
        existing_by_threshold.setdefault(alert.threshold, []).append(alert)

    new_by_threshold: Dict[float, List[ColdPeriod]] = {}
    for period in new_periods:
        new_by_threshold.setdefault(period.threshold, []).append(period)

    thresholds = set(existing_by_threshold.keys()) | set(new_by_threshold.keys())
    for threshold in sorted(thresholds, reverse=True):
        current_existing = sorted(existing_by_threshold.get(threshold, []), key=lambda a: a.start_date)
        current_new = sorted(new_by_threshold.get(threshold, []), key=lambda p: p.start_date)

        matched_ids: set[int] = set()

        for period in current_new:
            matched_alert: Optional[ColdPeriodAlert] = None
            for candidate in current_existing:
                if candidate.alert_id in matched_ids:
                    continue
                if _periods_overlap(period.start_date, period.end_date, candidate.start_date, candidate.end_date):
                    matched_alert = candidate
                    break

            if matched_alert is None:
                reason = "NEW_THRESHOLD" if _is_freeze_threshold(threshold) else "NEW_PERIOD"
                actions.append(
                    AlertAction(
                        action_type="CREATE",
                        period=period,
                        existing_alert_id=None,
                        notification_reason=reason,
                    )
                )
                continue

            matched_ids.add(matched_alert.alert_id)
            previous_period = _alert_to_period(matched_alert)
            reason, hours_extended, hours_shortened = _evaluate_period_changes(previous_period, period)

            if reason == "NO_CHANGE":
                actions.append(
                    AlertAction(
                        action_type="IGNORE",
                        period=period,
                        existing_alert_id=matched_alert.alert_id,
                        notification_reason=reason,
                        previous_period=previous_period,
                        previous_alert=matched_alert,
                    )
                )
                continue

            actions.append(
                AlertAction(
                    action_type="UPDATE",
                    period=period,
                    existing_alert_id=matched_alert.alert_id,
                    notification_reason=reason,
                    previous_period=previous_period,
                    previous_alert=matched_alert,
                    hours_extended=hours_extended,
                    hours_shortened=hours_shortened,
                )
            )

        for alert in current_existing:
            if alert.alert_id in matched_ids:
                continue
            previous_period = _alert_to_period(alert)
            actions.append(
                AlertAction(
                    action_type="DELETE",
                    period=previous_period,
                    existing_alert_id=alert.alert_id,
                    notification_reason="PERIOD_ENDED",
                    previous_period=previous_period,
                    previous_alert=alert,
                )
            )

    return actions


def should_notify(action: AlertAction, min_change_hours: int = 6) -> bool:
    """Détermine si une notification doit être envoyée pour l'action donnée."""

    if action.action_type == "IGNORE":
        return False

    if action.action_type == "CREATE":
        return True

    if action.action_type == "DELETE":
        return True

    if action.action_type != "UPDATE":
        return False

    reason = action.notification_reason
    if reason in {"PERIOD_EXTENDED", "NEW_THRESHOLD"}:
        return True

    if reason == "PERIOD_SHORTENED":
        if action.hours_shortened is None:
            return False
        return action.hours_shortened >= float(min_change_hours)

    if reason in {"MIN_TEMP_CHANGED", "PERIOD_SHIFTED"}:
        return True

    return False


def create_notification_messages(actions: List[AlertAction]) -> List[NotificationData]:
    """Crée les messages de notification associés aux actions."""

    notifications: List[NotificationData] = []

    for action in actions:
        threshold = action.period.threshold
        severity = "critical" if _is_freeze_threshold(threshold) else "warning"
        title = "🥶 Alerte gel" if severity == "critical" else "🌡️ Vigilance froid"

        if action.action_type == "CREATE":
            message = format_plant_alert_message(
                threshold=action.period.threshold,
                start_date=action.period.start_date,
                end_date=action.period.end_date,
                min_temp=action.period.min_temp,
            )
            message.description = _format_new_period_message(action.period)
            notifications.append(
                NotificationData(
                    action=action,
                    message=message,
                )
            )
            continue
        elif action.action_type == "UPDATE":
            description = _format_update_message(action)
        elif action.action_type == "DELETE":
            description = _format_end_message(action.previous_period)
            severity = "info"
            title = "✅ Fin période froide"
        else:
            continue

        message = NotificationMessage(
            title=title,
            description=description,
            severity=severity,
            timestamp=datetime.now(),
        )

        notifications.append(
            NotificationData(
                action=action,
                message=message,
            )
        )

    return notifications


def process_weather_alerts(config_path: Path) -> List[NotificationMessage]:
    """Pipeline complet de détection et de notification des périodes froides.

    Fonctionne toute l'année sans restriction saisonnière.
    """

    config = ConfigParser()
    config.read(config_path)

    vigilance_threshold = config.getfloat("thresholds", "vigilance", fallback=3.0)
    freeze_threshold = config.getfloat("thresholds", "freeze", fallback=0.0)
    configure_thresholds(vigilance_threshold, freeze_threshold)

    min_change_hours = config.getint("notifications", "min_change_threshold", fallback=6)

    db_manager = DatabaseManager.from_config(Path(config_path))
    db_manager.init_db()

    weather_client = MeteoFranceWeatherClient.from_config(Path(config_path))
    forecast = weather_client.get_forecast_48h()

    detected_periods = detect_cold_periods(forecast)
    existing_alerts = db_manager.get_active_alerts()

    actions = compare_periods(detected_periods, existing_alerts)

    _persist_actions(db_manager, actions)

    notifiable_actions = [action for action in actions if should_notify(action, min_change_hours)]

    notifications = create_notification_messages(notifiable_actions)

    for data in notifications:
        alert_id = data.action.existing_alert_id if data.action.action_type != "DELETE" else None
        db_manager.record_notification(alert_id, data.message.description, data.channels)
        if alert_id is not None:
            db_manager.update_last_notified(alert_id)

    return [data.message for data in notifications]


def _persist_actions(db_manager: DatabaseManager, actions: Iterable[AlertAction]) -> None:
    for action in actions:
        if action.action_type == "CREATE":
            alert_id = db_manager.save_alert(
                threshold=action.period.threshold,
                start_date=action.period.start_date,
                end_date=action.period.end_date,
                min_temp=action.period.min_temp,
                min_temp_date=action.period.min_temp_date,
            )
            action.existing_alert_id = alert_id
        elif action.action_type == "UPDATE":
            alert_id = action.existing_alert_id or (action.previous_alert.alert_id if action.previous_alert else None)
            if alert_id is None:
                LOGGER.warning("Alerte sans identifiant pour mise à jour – création forcée")
                alert_id = db_manager.save_alert(
                    threshold=action.period.threshold,
                    start_date=action.period.start_date,
                    end_date=action.period.end_date,
                    min_temp=action.period.min_temp,
                    min_temp_date=action.period.min_temp_date,
                )
                action.action_type = "CREATE"
                action.existing_alert_id = alert_id
                continue
            _update_alert_record(
                db_manager,
                alert_id,
                action.period,
            )
            action.existing_alert_id = alert_id
        elif action.action_type == "DELETE":
            if action.existing_alert_id is not None:
                db_manager.delete_alert(action.existing_alert_id)


def _alert_to_period(alert: ColdPeriodAlert) -> ColdPeriod:
    return ColdPeriod(
        threshold=alert.threshold,
        start_date=alert.start_date,
        end_date=alert.end_date,
        min_temp=alert.min_temp,
        min_temp_date=alert.min_temp_date,
    )


def _update_alert_record(db_manager: DatabaseManager, alert_id: int, period: ColdPeriod) -> None:
    with db_manager.connection() as conn:
        conn.execute(
            """
            UPDATE current_alerts
            SET start_date = ?, end_date = ?, min_temp = ?, min_temp_date = ?
            WHERE id = ?
            """,
            (
                period.start_date.isoformat(),
                period.end_date.isoformat(),
                float(period.min_temp),
                period.min_temp_date.isoformat(),
                alert_id,
            ),
        )


def _format_new_period_message(period: ColdPeriod) -> str:
    return (
        "📅 Période froide prévue : "
        f"{period.start_date.strftime('%d/%m %Hh')} → {period.end_date.strftime('%d/%m %Hh')}"
    )


def _format_update_message(action: AlertAction) -> str:
    if action.previous_period is None:
        return _format_new_period_message(action.period)

    previous = action.previous_period
    now_range = f"{action.period.start_date.strftime('%d/%m %Hh')} → {action.period.end_date.strftime('%d/%m %Hh')}"
    old_range = f"{previous.start_date.strftime('%d/%m %Hh')} → {previous.end_date.strftime('%d/%m %Hh')}"

    if action.notification_reason == "MIN_TEMP_CHANGED":
        return (
            "⚠️ Période froide modifiée : "
            f"mini {previous.min_temp:.1f}°C → {action.period.min_temp:.1f}°C"
        )

    return (
        "⚠️ Période froide modifiée : "
        f"était {old_range} → maintenant {now_range}"
    )


def _format_end_message(previous: Optional[ColdPeriod]) -> str:
    if previous is None:
        return "✅ Fin période froide : plus de risque prévu"

    old_range = f"{previous.start_date.strftime('%d/%m %Hh')} → {previous.end_date.strftime('%d/%m %Hh')}"
    return "✅ Fin période froide : plus de risque prévu (\u2744️ " + old_range + ")"


def _is_freeze_threshold(threshold: float) -> bool:
    freeze_values = [value for attr, value in _THRESHOLD_MAPPING if attr == "below_freeze"]
    if not freeze_values:
        return threshold <= 0.0
    return threshold <= freeze_values[0]


def _periods_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a <= end_b and start_b <= end_a


def _evaluate_period_changes(previous: ColdPeriod, current: ColdPeriod) -> Tuple[str, Optional[float], Optional[float]]:
    duration_previous = previous.duration_hours
    duration_current = current.duration_hours
    duration_delta = duration_current - duration_previous

    start_changed = previous.start_date != current.start_date
    end_changed = previous.end_date != current.end_date
    min_temp_changed = abs(previous.min_temp - current.min_temp) >= 0.1

    if not start_changed and not end_changed and not min_temp_changed:
        return "NO_CHANGE", None, None

    if duration_delta > 0.0:
        return "PERIOD_EXTENDED", duration_delta, None

    if duration_delta < 0.0:
        return "PERIOD_SHORTENED", None, abs(duration_delta)

    if start_changed or end_changed:
        return "PERIOD_SHIFTED", None, None

    if min_temp_changed:
        return "MIN_TEMP_CHANGED", None, None

    return "PERIOD_SHIFTED", None, None


__all__ = [
    "AlertAction",
    "ColdPeriod",
    "NotificationData",
    "compare_periods",
    "create_notification_messages",
    "detect_cold_periods",
    "process_weather_alerts",
    "should_notify",
]
