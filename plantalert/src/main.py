"""Point d'entrée principal de PlantAlert."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

if __package__:
    from .database import DatabaseManager
    from .weather import MeteoFranceWeatherClient
else:  # pragma: no cover - support exécution directe
    CURRENT_DIR = Path(__file__).resolve().parent
    if str(CURRENT_DIR) not in sys.path:
        sys.path.append(str(CURRENT_DIR))
    from database import DatabaseManager
    from weather import MeteoFranceWeatherClient

LOGGER = logging.getLogger(__name__)


def main() -> None:
    """Point d'entrée principal."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Mode test")
    parser.add_argument("--config", default="config/settings.ini")
    args = parser.parse_args()

    config_path = Path(args.config)

    if args.test:
        print("=== TEST PlantAlert ===")

        db = DatabaseManager.from_config(config_path)
        db.init_db()
        print(f"✅ Base : {db.db_path}")

        weather = MeteoFranceWeatherClient.from_config(config_path)
        forecast = weather.get_forecast_48h()
        print(f"✅ Météo : {len(forecast)} heures récupérées")

        if __package__:
            from .notifications import format_plant_alert_message
        else:  # pragma: no cover
            from notifications import format_plant_alert_message

        msg = format_plant_alert_message(3.0, datetime.now(), datetime.now(), 1.5)
        print(f"✅ Notification : {msg.title}")

        return

    LOGGER.warning("Logique métier pas encore implémentée. Utiliser --test")


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    main()
