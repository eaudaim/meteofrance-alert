# Documentation DevOps - Système d'alerte plantes

## 🎯 Objectif
Système automatisé d'alerte pour protéger les plantes du froid en analysant les prévisions météo et notifiant l'utilisateur des périodes de risque.

## 📋 Spécifications fonctionnelles

### Seuils de température
- **3°C** : Vigilance (plantes sensibles à rentrer)
- **0°C** : Gel (urgence, toutes plantes fragiles)

### Période active
- **1er septembre → 1er mai** (saison froide)

### Anticipation
- **48h** à l'avance maximum

### Logique d'alerte
- Détection de **périodes froides** (séquences continues)
- Notification des **changements significatifs** de période
- **Anti-spam** : pas de notification pour changements mineurs (<6h raccourcissement)
- **Toujours notifier** : allongement de période, nouveau seuil atteint

### Notifications
- **Discord webhook** (mobile)
- **notify-send** (PC Linux Mint)
- **Double notification** systématique

## 🏗️ Architecture technique

### Plateforme
- **Raspberry Pi** (H24, déjà configuré avec OpenVPN/Transmission)
- **Système** : Debian/Raspbian
- **Déploiement** : systemd service + timer

### Stack technique
- **Python 3.9+** (zoneinfo pour les timezones)
- **meteofrance_api** (API météo)
- **SQLite** (état des alertes)
- **requests** (webhook Discord)
- **subprocess** (notify-send si PC accessible)

### Base de données (SQLite)
```sql
-- Table principale des alertes actives
CREATE TABLE current_alerts (
    id INTEGER PRIMARY KEY,
    threshold REAL NOT NULL,           -- 3.0 ou 0.0
    start_date TEXT NOT NULL,          -- ISO format UTC
    end_date TEXT NOT NULL,            -- ISO format UTC
    min_temp REAL NOT NULL,            -- Température minimale prévue
    min_temp_date TEXT NOT NULL,       -- Quand aura lieu le minimum
    created_at TEXT NOT NULL,          -- Création de l'alerte
    last_notified_at TEXT              -- Dernière notification envoyée
);

-- Historique des notifications
CREATE TABLE notification_history (
    id INTEGER PRIMARY KEY,
    alert_id INTEGER,
    message TEXT NOT NULL,
    channels TEXT NOT NULL,            -- "discord,notify" 
    sent_at TEXT NOT NULL,
    FOREIGN KEY (alert_id) REFERENCES current_alerts (id)
);

-- Cache des prévisions
CREATE TABLE forecast_cache (
    id INTEGER PRIMARY KEY,
    forecast_data TEXT NOT NULL,       -- JSON des prévisions
    fetched_at TEXT NOT NULL
);
```

## 🔧 Installation et configuration

### 1. Prérequis système (Raspberry Pi)
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv sqlite3 libnotify-bin
```

### 2. Setup projet
```bash
# Créer utilisateur dédié (optionnel, sécurité)
sudo useradd -r -s /bin/false plantalert
sudo mkdir -p /opt/plantalert
sudo chown plantalert:plantalert /opt/plantalert

# Ou utiliser l'utilisateur pi existant
mkdir -p ~/plantalert
cd ~/plantalert

# Environnement virtuel Python
python3 -m venv venv
source venv/bin/activate
pip install meteofrance_api requests
```

### 3. Configuration Discord
```bash
# 1. Créer serveur Discord privé "Alertes Maison"
# 2. Créer salon #alertes-plantes  
# 3. Paramètres salon → Intégrations → Webhooks → Nouveau webhook
# 4. Copier l'URL du webhook
# 5. Tester : curl -X POST -H "Content-Type: application/json" \
#    -d '{"content":"🧪 Test alerte plantes"}' \
#    "WEBHOOK_URL"
```

### 4. Configuration notify-send (PC)
```bash
# Vérifier accès SSH au PC depuis Raspberry
ssh user@pc-ip "notify-send 'Test' 'Alerte depuis Raspberry'"

# Ou configuration X11 forwarding si nécessaire
# ~/.ssh/config sur le Raspberry :
# Host pc-home
#   HostName 192.168.1.xxx
#   User votre_user
#   ForwardX11 yes
```

## 📁 Structure du projet

```
/opt/plantalert/  (ou ~/plantalert/)
├── venv/                    # Environnement Python
├── config/
│   └── settings.ini         # Configuration
├── src/
│   ├── main.py             # Point d'entrée principal
│   ├── weather.py          # Interface Météo France
│   ├── database.py         # Gestion SQLite
│   ├── alerts.py           # Logique d'alerte
│   └── notifications.py    # Discord + notify-send
├── data/
│   └── alerts.db           # Base SQLite
├── logs/                   # Logs applicatifs
└── scripts/
    ├── install.sh          # Script d'installation
    └── backup.sh           # Sauvegarde config/data
```

## ⚙️ Configuration (settings.ini)

```ini
[location]
# Lieu des prévisions météo
city = Collonges-au-Mont-d'Or

[thresholds]
# Seuils de température (°C)
vigilance = 3.0
freeze = 0.0

[timing]
# Période active (MM-DD format)
start_date = 09-01
end_date = 05-01
# Anticipation maximale (heures)
forecast_hours = 48
# Fréquence vérification (heures)
check_interval = 12

[notifications]
# Discord webhook URL
discord_webhook = https://discord.com/api/webhooks/xxxxx
# PC pour notify-send (vide = désactivé)
pc_ssh_host = user@192.168.1.xxx
# Anti-spam : seuil changement minimal (heures)
min_change_threshold = 6

[database]
# Chemin base SQLite
db_path = data/alerts.db

[logging]
# Niveau : DEBUG, INFO, WARNING, ERROR
level = INFO
# Rotation des logs
max_size_mb = 10
backup_count = 5
```

## 🚀 Déploiement systemd

### Service principal (/etc/systemd/system/plantalert.service)
```ini
[Unit]
Description=Plant Cold Alert System
After=network.target

[Service]
Type=oneshot
User=plantalert
WorkingDirectory=/opt/plantalert
Environment=PATH=/opt/plantalert/venv/bin
ExecStart=/opt/plantalert/venv/bin/python src/main.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Timer systemd (/etc/systemd/system/plantalert.timer)
```ini
[Unit]
Description=Run Plant Alert Check twice daily
Requires=plantalert.service

[Timer]
# Vérifications à 8h et 20h
OnCalendar=08:00
OnCalendar=20:00
# Rattrapage si système éteint
Persistent=true

[Install]
WantedBy=timers.target
```

### Activation
```bash
sudo systemctl daemon-reload
sudo systemctl enable plantalert.timer
sudo systemctl start plantalert.timer

# Vérification
sudo systemctl status plantalert.timer
sudo journalctl -u plantalert -f
```

## 📊 Monitoring et maintenance

### Logs
```bash
# Logs systemd
sudo journalctl -u plantalert -f

# Logs applicatifs
tail -f /opt/plantalert/logs/plantalert.log

# Vérifier timer
sudo systemctl list-timers | grep plantalert
```

### Tests manuels
```bash
# Test complet
cd /opt/plantalert
source venv/bin/activate
python src/main.py --test

# Test notifications seules
python src/notifications.py --test-discord
python src/notifications.py --test-notify
```

### Sauvegarde
```bash
# Script de sauvegarde quotidien
#!/bin/bash
DATE=$(date +%Y%m%d)
tar -czf /backup/plantalert-$DATE.tar.gz \
    /opt/plantalert/config/ \
    /opt/plantalert/data/ \
    /opt/plantalert/logs/
```

## 🐛 Troubleshooting

### Problèmes fréquents

**API Météo France inaccessible**
- Vérifier connexion internet
- Tester manuellement : `curl -I https://meteofrance.com`
- Logs : rechercher "HTTP" ou "timeout"

**Discord webhook échoue**
- Tester webhook : `curl -X POST -H "Content-Type: application/json" -d '{"content":"test"}' WEBHOOK_URL`
- Vérifier URL dans config
- Logs : rechercher "discord" ou "webhook"

**notify-send ne fonctionne pas**
- Vérifier SSH vers PC : `ssh user@pc "echo OK"`
- Tester : `ssh user@pc "notify-send 'Test' 'Message'"`
- Vérifier DISPLAY si nécessaire

**Alertes en double**
- Vérifier base données : `sqlite3 data/alerts.db "SELECT * FROM current_alerts;"`
- Nettoyer si nécessaire : `python src/database.py --cleanup`

**Service ne démarre pas**
- Permissions : `sudo chown -R plantalert:plantalert /opt/plantalert`
- Logs : `sudo journalctl -u plantalert --no-pager`
- Test manuel : `sudo -u plantalert /opt/plantalert/venv/bin/python /opt/plantalert/src/main.py`

### Debug avancé
```bash
# Mode verbose
python src/main.py --debug

# Test avec données fictives
python src/main.py --mock-weather="-2,1,3"

# Reset complet alertes
python src/database.py --reset-alerts
```

## 🔄 Versions et mises à jour

### Version actuelle : 1.0.0

**Roadmap futures versions :**
- v1.1 : Interface web pour configuration
- v1.2 : Multiples emplacements
- v1.3 : Intégration capteurs IoT réels

### Mise à jour
```bash
cd /opt/plantalert
git pull  # Si versioning Git
sudo systemctl restart plantalert.timer
```

---

**Dernière mise à jour :** 26/09/2025  
**Responsable :** Assistant Claude + Utilisateur  
**Contact support :** Logs systemd + GitHub issues
