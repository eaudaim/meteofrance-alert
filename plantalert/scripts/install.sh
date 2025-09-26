#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
SERVICE_NAME="plantalert"
USER_NAME="val"
PYTHON_BIN="python3"

apt_packages=(
  python3
  python3-venv
  python3-pip
  sqlite3
)

install_system_packages() {
  echo "[+] Installation des paquets systèmes : ${apt_packages[*]}"
  sudo apt-get update
  sudo apt-get install -y "${apt_packages[@]}"
}

create_virtualenv() {
  if [[ ! -d "$VENV_PATH" ]]; then
    echo "[+] Création de l'environnement virtuel"
    "$PYTHON_BIN" -m venv "$VENV_PATH"
  fi
  # shellcheck source=/dev/null
  source "$VENV_PATH/bin/activate"
  pip install --upgrade pip
  pip install -r "$PROJECT_ROOT/requirements.txt"
}

setup_directories() {
  echo "[+] Préparation des répertoires"
  sudo mkdir -p "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs"
  sudo chown -R "$USER_NAME":"$USER_NAME" "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs"
}

create_systemd_timer() {
  echo "[+] Création des unités systemd pour PlantAlert"
  # Service oneshot
  sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<SERVICE
[Unit]
Description=Plant Cold Alert Check
After=network.target

[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=/home/$USER_NAME/plantalert
Environment=PATH=/home/$USER_NAME/plantalert/venv/bin
ExecStart=/home/$USER_NAME/plantalert/venv/bin/python src/main.py
StandardOutput=journal
StandardError=journal
SERVICE

  # Timer 2x/jour
  sudo tee "/etc/systemd/system/${SERVICE_NAME}.timer" >/dev/null <<TIMER
[Unit]
Description=Run Plant Alert Check twice daily
Requires=${SERVICE_NAME}.service

[Timer]
OnCalendar=08:00
OnCalendar=20:00
Persistent=true

[Install]
WantedBy=timers.target
TIMER

  sudo systemctl daemon-reload
  sudo systemctl enable ${SERVICE_NAME}.timer
}

initialize_database() {
  echo "[+] Initialisation de la base de données"
  "$VENV_PATH/bin/python" src/database.py init --config "$PROJECT_ROOT/config/settings.ini"
}

main() {
  install_system_packages
  create_virtualenv
  setup_directories
  initialize_database
  create_systemd_timer
  echo "[+] Installation terminée. Utiliser 'sudo systemctl start ${SERVICE_NAME}.timer' pour activer les vérifications."
}

main "$@"
