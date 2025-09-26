"""Logique métier des alertes.

La mise en œuvre complète sera ajoutée dans une prochaine itération.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List


@dataclass(slots=True)
class Alert:
    """Représentation minimale d'une alerte météo."""

    created_at: datetime
    message: str
    severity: str


def evaluate_conditions(*_args, **_kwargs) -> List[Alert]:
    """Placeholder pour l'évaluation des conditions météo."""

    return []


def get_pending_alerts(_alerts: Iterable[Alert]) -> List[Alert]:
    """Retourne la liste des alertes en attente d'envoi.

    Cette fonction sera enrichie lorsque la logique métier sera disponible.
    """

    return list(_alerts)
