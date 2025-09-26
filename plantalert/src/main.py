"""Point d'entrée principal de PlantAlert (orchestration complète)."""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys
import time
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

if __package__:
    from .alerts import process_weather_alerts
    from .database import DatabaseManager
    from .notifications import (
        NotificationMessage,
        format_plant_alert_message,
        send_discord_webhook,
        send_notify_send,
    )
    from .weather import MeteoFranceWeatherClient
else:  # pragma: no cover - support exécution directe
    CURRENT_DIR = Path(__file__).resolve().parent
    if str(CURRENT_DIR) not in sys.path:
        sys.path.append(str(CURRENT_DIR))
    from alerts import process_weather_alerts
    from database import DatabaseManager
    from notifications import (
        NotificationMessage,
        format_plant_alert_message,
        send_discord_webhook,
        send_notify_send,
    )
    from weather import MeteoFranceWeatherClient

LOGGER = logging.getLogger(__name__)
_PLACEHOLDER_WEBHOOK = "https://discord.com/api/webhooks/CHANGEME"
_PLACEHOLDER_SSH = "val@192.168.1.100"


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments CLI."""

    parser = argparse.ArgumentParser(description="PlantAlert – notifications météo")
    parser.add_argument("--test", action="store_true", help="Mode test complet")
    parser.add_argument(
        "--config",
        default="config/settings.ini",
        help="Chemin du fichier de configuration",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exécute le workflow sans envoyer les notifications",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def load_config(config_path: Path) -> ConfigParser:
    """Charge le fichier de configuration."""

    if not config_path.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable: {config_path}")

    config = ConfigParser()
    config.read(config_path)
    return config


def configure_logging(config: ConfigParser) -> None:
    """Configure le logging à partir de la configuration."""

    log_level_name = config.get("logging", "level", fallback="INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_file = Path(config.get("logging", "log_file", fallback="logs/plantalert.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)

    max_size_mb = config.getint("logging", "max_size_mb", fallback=10)
    backup_count = config.getint("logging", "backup_count", fallback=5)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=max(1, max_size_mb) * 1024 * 1024,
        backupCount=max(1, backup_count),
        encoding="utf-8",
    )

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )


def send_discord_notifications(
    messages: Iterable[NotificationMessage],
    webhook_url: str,
    *,
    dry_run: bool = False,
) -> List[bool]:
    """Envoie les notifications vers Discord."""

    messages_list = list(messages)
    results: List[bool] = []

    if not webhook_url or webhook_url.strip() == "":
        if messages_list:
            LOGGER.info(
                "Webhook Discord non configuré. %d messages ignorés.",
                len(messages_list),
            )
        return []

    webhook_url = webhook_url.strip()
    if webhook_url == _PLACEHOLDER_WEBHOOK:
        LOGGER.info(
            "Webhook Discord de placeholder, envoi ignoré pour %d messages.",
            len(messages_list),
        )
        return []

    for message in messages_list:
        if dry_run:
            LOGGER.info("[DRY-RUN] Discord → %s", message.title)
            results.append(True)
            continue

        success = send_discord_webhook(webhook_url, message)
        if success:
            LOGGER.info("Notification Discord envoyée: %s", message.title)
        else:
            LOGGER.error("Echec notification Discord: %s", message.title)
        results.append(success)

    return results


def send_notify_send_ssh(message: NotificationMessage, ssh_host: str) -> bool:
    """Envoie une notification notify-send sur un hôte distant via SSH."""

    ssh_host = ssh_host.strip()
    if not ssh_host:
        return send_notify_send(message)

    if ssh_host in {"local", "localhost"}:
        return send_notify_send(message)

    command = ["ssh", ssh_host, *message.to_notify_send_args()]
    try:
        subprocess.run(command, check=True, timeout=20)
    except subprocess.TimeoutExpired as exc:
        LOGGER.error("Timeout SSH notify-send pour %s: %s", ssh_host, exc)
        return False
    except (subprocess.CalledProcessError, OSError) as exc:
        LOGGER.error("Erreur SSH notify-send pour %s: %s", ssh_host, exc)
        return False

    LOGGER.info("Notification notify-send envoyée via SSH (%s): %s", ssh_host, message.title)
    return True


def send_notify_notifications(
    messages: Iterable[NotificationMessage],
    ssh_host: str,
    *,
    dry_run: bool = False,
) -> List[bool]:
    """Envoie les notifications via notify-send (SSH si configuré)."""

    messages_list = list(messages)
    if not ssh_host or ssh_host.strip() == "":
        if messages_list:
            LOGGER.info(
                "Aucun hôte SSH configuré, %d notifications notify-send ignorées.",
                len(messages_list),
            )
        return []

    ssh_host = ssh_host.strip()
    if ssh_host == _PLACEHOLDER_SSH:
        LOGGER.info(
            "Hôte SSH de placeholder, envoi notify-send ignoré pour %d messages.",
            len(messages_list),
        )
        return []

    results: List[bool] = []
    for message in messages_list:
        if dry_run:
            LOGGER.info("[DRY-RUN] notify-send → %s", message.title)
            results.append(True)
            continue

        success = send_notify_send_ssh(message, ssh_host)
        if not success:
            LOGGER.error("Echec notify-send pour: %s", message.title)
        results.append(success)

    return results


def run_tests(config_path: Path, config: ConfigParser) -> int:
    """Exécute les tests end-to-end."""

    print("=== TEST PlantAlert ===")

    db_manager = DatabaseManager.from_config(config_path)
    db_manager.init_db()
    print(f"✅ Base : {db_manager.db_path}")

    weather_client = MeteoFranceWeatherClient.from_config(config_path)
    forecast = weather_client.get_forecast_48h()
    print(f"✅ Météo : {len(forecast)} heures récupérées")

    message = format_plant_alert_message(3.0, datetime.now(), datetime.now(), 1.5)
    print(f"✅ Notification : {message.title}")

    notifications = process_weather_alerts(config_path)
    print(f"✅ Workflow : {len(notifications)} notifications générées")

    test_message = NotificationMessage(
        title="🧪 Test PlantAlert",
        description="Test complet workflow PlantAlert",
        severity="info",
        timestamp=datetime.now(),
    )

    webhook_url = config.get("notifications", "discord_webhook", fallback="").strip()
    if webhook_url and webhook_url != _PLACEHOLDER_WEBHOOK:
        success = send_discord_webhook(webhook_url, test_message)
        print(f"✅ Discord : {'OK' if success else 'ERREUR'}")
    else:
        print("ℹ️ Discord : webhook non configuré, test ignoré")

    ssh_host = config.get("notifications", "pc_ssh_host", fallback="").strip()
    if ssh_host and ssh_host != _PLACEHOLDER_SSH:
        success = send_notify_send_ssh(test_message, ssh_host)
        print(f"✅ Notify : {'OK' if success else 'ERREUR'}")
    else:
        print("ℹ️ Notify : hôte SSH non configuré, test ignoré")

    return 0


def execute_workflow(config_path: Path, config: ConfigParser, *, dry_run: bool) -> int:
    """Exécute le workflow principal de production."""

    start_time = time.perf_counter()
    try:
        messages = process_weather_alerts(config_path)
    except Exception:
        LOGGER.exception("Echec lors de l'analyse des alertes météo")
        return 1

    LOGGER.info("%d notifications à traiter", len(messages))

    if not messages:
        duration = time.perf_counter() - start_time
        LOGGER.info("Aucune notification générée. Durée: %.2fs", duration)
        return 0

    webhook_url = config.get("notifications", "discord_webhook", fallback="")
    ssh_host = config.get("notifications", "pc_ssh_host", fallback="")

    discord_results = send_discord_notifications(messages, webhook_url, dry_run=dry_run)
    notify_results = send_notify_notifications(messages, ssh_host, dry_run=dry_run)

    sent_discord = sum(1 for result in discord_results if result)
    failed_discord = sum(1 for result in discord_results if result is False)

    sent_notify = sum(1 for result in notify_results if result)
    failed_notify = sum(1 for result in notify_results if result is False)

    duration = time.perf_counter() - start_time
    LOGGER.info(
        "Workflow terminé en %.2fs - Discord: %s/%s, notify-send: %s/%s",
        duration,
        sent_discord,
        len(discord_results),
        sent_notify,
        len(notify_results),
    )

    if failed_discord or failed_notify:
        LOGGER.warning(
            "Erreurs lors de l'envoi des notifications (Discord: %s, notify-send: %s)",
            failed_discord,
            failed_notify,
        )
        return 1 if not dry_run else 0

    return 0


def _run(argv: Iterable[str] | None = None) -> int:
    """Routine principale commune."""

    args = parse_args(argv)
    config_path = Path(args.config).expanduser().resolve()

    try:
        config = load_config(config_path)
    except Exception:
        logging.basicConfig(level=logging.ERROR)
        LOGGER.exception("Impossible de charger la configuration")
        return 1

    configure_logging(config)
    LOGGER.info(
        "Démarrage PlantAlert (test=%s, dry_run=%s) avec config %s",
        args.test,
        args.dry_run,
        config_path,
    )

    try:
        if args.test:
            return run_tests(config_path, config)
        return execute_workflow(config_path, config, dry_run=args.dry_run)
    except Exception:
        LOGGER.exception("Erreur inattendue dans le workflow PlantAlert")
        return 1


def main() -> None:
    """Workflow principal : analyse météo + notifications + logging."""

    exit_code = _run()
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":  # pragma: no cover
    main()
