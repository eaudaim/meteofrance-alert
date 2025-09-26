# PlantAlert

PlantAlert est une base de projet pour surveiller les conditions météorologiques et prévenir les cultivateurs en cas de conditions critiques. Cette première itération met en place la structure logicielle, la configuration et les composants d'infrastructure nécessaires pour développer la logique métier dans des étapes ultérieures.

## Structure du projet

```
plantalert/
├── config/
│   └── settings.ini
├── src/
│   ├── alerts.py
│   ├── database.py
│   ├── main.py
│   ├── notifications.py
│   ├── weather.py
│   └── __init__.py
├── data/
├── logs/
├── scripts/
│   ├── backup.sh
│   └── install.sh
├── requirements.txt
└── README.md
```

Les répertoires `data/` et `logs/` sont initialement vides et seront alimentés respectivement par la base SQLite (`alerts.db`) et les fichiers de logs applicatifs.

## Prise en main rapide

1. **Créer l'environnement virtuel**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Configurer l'application**
   - Adapter `config/settings.ini` pour refléter vos besoins (seuils météo, notifications, etc.).
   - Les paramètres de localisation ciblent Collonges-au-Mont-d'Or et utilisent la timezone `Europe/Paris`.

3. **Initialiser la base de données**
   ```bash
   python -m plantalert.src.database init
   ```
   Cette commande crée les tables nécessaires dans `data/alerts.db`.

4. **Déploiement système**
   - Le script `scripts/install.sh` automatise l'installation des dépendances système, la création du service `systemd` et l'initialisation du projet.
   - Adapter les chemins et utilisateurs dans le script avant exécution sur votre serveur.

## Tests

Les modules sont conçus pour être testables individuellement. Des tests unitaires seront ajoutés lorsque la logique métier (`alerts.py`, `main.py`) sera implémentée.

## Licence

Ce projet est fourni tel quel pour usage interne dans le cadre du DevOps PlantAlert.
