#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data"
BACKUP_DIR="$PROJECT_ROOT/backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DB_FILE="$DATA_DIR/alerts.db"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_FILE" ]]; then
  echo "[!] Base de données introuvable: $DB_FILE" >&2
  exit 1
fi

target="$BACKUP_DIR/alerts-$TIMESTAMP.sqlite"

sqlite3 "$DB_FILE" ".backup '$target'"

echo "[+] Sauvegarde créée: $target"

