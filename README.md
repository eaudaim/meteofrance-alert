# PlantAlert – Alerte Gel & Froid Automatisée

PlantAlert surveille les prévisions Météo-France et envoie des notifications (Discord et notify-send) lorsque des épisodes de froid sont anticipés. Ce guide détaille **l'installation de bout en bout** ainsi que **l'ensemble des commandes disponibles** pour administrer le service.

## 📦 Prérequis

- Raspberry Pi / serveur Debian ou Ubuntu avec accès internet
- Python **3.9 ou supérieur**
- Accès `sudo` pour installer les dépendances système
- Webhook Discord valide (facultatif mais recommandé)
- Accès SSH vers le PC cible si utilisation de `notify-send`

Les dépendances système minimales sont installées automatiquement par le script (`python3`, `python3-venv`, `python3-pip`, `sqlite3`). Pour une installation manuelle, assurez-vous qu'elles sont présentes avant de continuer.

## 🚀 Installation

1. **Cloner le dépôt et se placer dans le projet**
   ```bash
   git clone https://github.com/<votre-compte>/meteofrance-alert.git
   cd meteofrance-alert/plantalert
   ```

2. **Configurer les variables essentielles**
   - Ouvrir `config/settings.ini` et renseigner :
     - `location.city` et `location.timezone`
     - `notifications.discord_webhook` (URL du webhook)
     - `notifications.pc_ssh_host` (ex. `utilisateur@192.168.1.50` ou `local`)
   - Ajuster les seuils, la période de surveillance et les paramètres de log si besoin.

3. **Installation automatisée (recommandée)**
   ```bash
   ./scripts/install.sh
   ```
   Le script réalise les actions suivantes :
   - Installe les paquets APT requis
   - Crée l'environnement virtuel `venv/` et installe `requirements.txt`
   - Prépare les répertoires `data/` et `logs/`
   - Initialise la base SQLite
   - Installe et active le service/timer systemd `plantalert` (exécutions à 08h et 20h)

   > ℹ️ Par défaut le script crée un service pour l'utilisateur `val`. Modifiez `USER_NAME` dans `scripts/install.sh` si nécessaire avant exécution.

4. **Installation manuelle (alternative)**
   ```bash
   sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip sqlite3

   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt

   # Initialisation de la base
   python src/database.py init --config config/settings.ini
   ```
   Créez ensuite vos propres unités `systemd` ou planifiez un `cron` selon vos besoins (exemple fourni dans `scripts/install.sh`).

## ▶️ Utilisation & commandes

Toutes les commandes doivent être lancées depuis `plantalert/` avec l'environnement virtuel activé (`source venv/bin/activate`).

### 1. Exécution principale
```bash
python src/main.py [options]
```
Options disponibles :
- `--config <chemin>` : chemin vers un fichier de configuration alternatif (par défaut `config/settings.ini`).
- `--dry-run` : exécute tout le pipeline sans envoyer les notifications (utile pour valider la configuration).
- `--test` : lance un test complet (incluant la récupération météo et la logique d'alerte) puis quitte.

### 2. Maintenance de la base de données
```bash
python src/database.py init --config config/settings.ini
```
Initialise ou réinitialise la base SQLite définie dans la configuration.

### 3. Sauvegardes
```bash
./scripts/backup.sh
```
Crée une sauvegarde horodatée de `data/alerts.db` dans `backups/`. Le script échoue explicitement si la base est absente.

### 4. Services systemd (si installés via `install.sh`)
```bash
sudo systemctl start plantalert.timer     # démarrer les vérifications programmées
sudo systemctl stop plantalert.timer      # arrêter les vérifications
sudo systemctl status plantalert.timer    # état du timer
sudo journalctl -u plantalert -f          # suivre les logs en direct
```
Le service `plantalert.service` est exécuté deux fois par jour (`08:00`, `20:00`). Modifiez les horaires dans `/etc/systemd/system/plantalert.timer` si nécessaire, puis rechargez la configuration (`sudo systemctl daemon-reload`).

### 5. Vérifications ponctuelles
```bash
sudo -u <user> /home/<user>/plantalert/venv/bin/python src/main.py --dry-run
```
Permet de tester l'exécution depuis l'utilisateur du service sans déclencher de notifications réelles.

## 🧪 Conseils de test
- `python src/main.py --dry-run --test` : simulation complète avec logs détaillés sans notifications.
- `python src/main.py --test` : vérifie le workflow en conditions réelles.
- `python src/main.py --dry-run` : vérifie uniquement la logique et l'accès base/API.

## 🛠️ Dépannage rapide
- `sudo journalctl -u plantalert --no-pager` : afficher les logs historiques du service.
- `tail -f logs/plantalert.log` : suivre les logs applicatifs.
- `sqlite3 data/alerts.db "SELECT * FROM current_alerts;"` : inspecter les alertes actives.

## ♻️ Mise à jour
```bash
cd /home/<user>/plantalert
source venv/bin/activate
git pull
pip install -r requirements.txt
sudo systemctl restart plantalert.timer
```

## 📁 Structure du projet
```
plantalert/
├── config/             # Configuration (settings.ini)
├── data/               # Base SQLite (alerts.db)
├── logs/               # Fichiers de log
├── scripts/            # install.sh, backup.sh
├── src/                # Code applicatif (main.py, database.py, ...)
└── requirements.txt    # Dépendances Python
```

## ✅ Résumé des commandes disponibles
| Commande | Description |
| --- | --- |
| `./scripts/install.sh` | Installation automatisée + configuration systemd |
| `python src/main.py [--config ...] [--dry-run] [--test]` | Lancement manuel du workflow |
| `python src/database.py init --config config/settings.ini` | Initialisation / reset de la base |
| `./scripts/backup.sh` | Sauvegarde horodatée de la base SQLite |
| `sudo systemctl {start,stop,status} plantalert.timer` | Gestion du timer systemd |
| `sudo journalctl -u plantalert -f` | Suivi temps réel des logs systemd |
| `tail -f logs/plantalert.log` | Suivi des logs applicatifs |
| `sqlite3 data/alerts.db "SELECT * FROM current_alerts;"` | Inspection des alertes enregistrées |

Ce document doit permettre de déployer rapidement PlantAlert et de disposer de toutes les commandes utiles pour l'exploitation quotidienne. Bonnes cultures !
