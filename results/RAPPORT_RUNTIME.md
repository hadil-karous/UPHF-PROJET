# Rapport de validation — ExFMD-CP — 4 novembre 2026

**Dashboard actif : http://127.0.0.1:8765/dashboard/**

Dernière relance automatisée réussie : `results/integrated/run-20261104-193341/`. La simulation est terminée ; les trois conteneurs du projet et le serveur de résultats restent actifs. Le dashboard présente des données enregistrées, pas un flux direct.

| Composant | Installé / lancé / testé | Résultat vérifié |
|---|---|---|
| CARLA 0.9.16 / Gyrovia | Oui / oui / oui | 3 véhicules visibles sur la chaussée ; captures extérieures et embarquées |
| SUMO 1.19 | Oui / terminé / oui | 75 pas, 225 positions ; hero 4,719 m ; vitesse max tous véhicules 4,000 m/s |
| ROS 2 Humble | Oui / testé puis terminé / oui | Messages capteurs, perception, CAM ETSI et CPM RAW effectivement reçus |
| Artery / OMNeT++ | Oui / scénario terminé / oui | Version OMNeT++ réelle 5.6.2 ; une RSU avec 116 CAM reçus et 39 émis |
| CAM / CPM | Oui / terminés / oui avec limites | 113 CAM décodés ROS, 38 paquets CPM RAW ROS ; décodage CPM r2 au détecteur historique non validé |
| FusionDetector | Oui / terminé / oui | Deux voitures suivies depuis LiDAR et caméra sémantiques ; pas de PointPillars |
| F2MD | Oui / diagnostics séparés terminés / partiel | Chaîne native radar/CPM historique : 114 réceptions, 76 checkfailed, 38 fichiers d'alerte ; pas couplé aux CPM r2 CARLA |
| Dashboard | Oui / oui / HTTP et JS testés | Captures, relecture, vitesse, nuage LiDAR, statistiques ROS/RSU, graphiques et F2MD séparé |

## Résultats visibles

Sous `D:\ExFMD-CP\results\integrated\run-20261104-193341\` :

- `overview.png` : trois véhicules sur Gyrovia.
- `onboard.png` : caméra embarquée.
- `lidar.ply` et `lidar.png` : échantillon réel et représentation 3D.
- `positions.csv` : pas, frame CARLA, temps SUMO, identifiant, XYZ, vitesse et erreur de pose.
- `measurements.png` et `measurements.svg` : trajectoires, vitesses et écarts spatiaux.
- `ros-messages.jsonl` : messages reçus horodatés, dont CAM décodés, CPM bruts hexadécimaux, GNSS/IMU et perception.
- `ros.log`, `artery.log`, `omnet-results/General-#0.sca` : journaux et compteurs radio.
- `report.json` : synthèse mesurée, nœuds, topics, compteurs et sortie FusionDetector.

Erreur spatiale maximale : **1,966e-6 m**. Temps mural mesuré de la partie ROS/CARLA : **83,412 s**, incluant l'initialisation et les attentes ; ne constitue pas une mesure de débit pur. Aucun écart d'horloge bout en bout n'est revendiqué. Le couplage impose les poses CARLA depuis SUMO et ne teste pas la physique libre des véhicules.

Données F2MD séparées : `D:\ExFMD-CP\results\f2md-native-probe\`, avec `report.json`, `probe.log`, journaux CPM sous `output/GENUINE/CPM/RX/Genuine/` et fichiers `alert_*.json`. Les alertes sont produites par le véritable service compilé, sans fabrication. Elles apparaissent dans un scénario Genuine ; la validité des alarmes n'est pas établie. Les fichiers utilisent le seul instant comme nom et peuvent être écrasés par plusieurs récepteurs : 38 fichiers ne signifient pas 38 décisions. Le dashboard les distingue des résultats CARLA intégrés.

## Validation effectuée

Les trois images existantes ont été inspectées. Le scénario d'origine a été tenté, avec erreurs conservées sous `runtime-audit/`. Une variante explicite Gyrovia utilisant les services compilés a terminé successivement avec un puis trois véhicules. Le script d'arrêt puis le nouveau script principal ont été exécutés et une relance à trois véhicules a terminé avec les mêmes mesures principales. Les captures et graphiques ont été inspectés. Le dashboard et ses huit ressources principales répondent HTTP 200 ; son JavaScript, les scripts Python et PowerShell ainsi que Compose passent les vérifications de syntaxe. Aucune automatisation de navigateur n'était disponible pour tester visuellement tous les contrôles.

## Relance

```powershell
cd D:\ExFMD-CP
powershell -ExecutionPolicy Bypass -File .\scripts\start-exfmd.ps1 -Vehicles 3 -OpenDashboard
```

Pour consulter sans relancer : `powershell -ExecutionPolicy Bypass -File .\scripts\start-dashboard.ps1 -Open`.

Pour arrêter ROS/Artery : `powershell -ExecutionPolicy Bypass -File .\scripts\stop-exfmd.ps1`. CARLA et les autres projets sont préservés ; ajouter `-StopDashboard` pour arrêter également le serveur HTTP.

## Limites restantes

La variante ne prétend pas reproduire intégralement le scénario d'origine, dont les chemins, roots NED, routes et paramètres sont incomplets ou obsolètes. La chaîne r2 CarlaPerceptionService vers F2MD historique doit être adaptée et validée. Aucun topic `/v2x_alert`, `/its/cpm_received` ni pont d'alertes n'est déclaré fonctionnel. Le système ROS utilise des timers muraux, sans `/clock` partagé. Les ports RAW sont des slots de création, pas des identités de véhicules, et le quatrième slot n'est pas écouté par les bridges d'origine. Voir `README_runtime.md` pour les détails et les fichiers nécessaires.

Fichiers ajoutés : Compose runtime, lanceurs/arrêts/état PowerShell, scripts de scénario et diagnostics, serveur/dashboard local, export de graphiques, README et ce rapport. Les résultats historiques et le dossier demo préexistant sont conservés. Aucun conteneur des autres projets n'a été modifié ; aucun téléchargement CARLA ni reconstruction Unreal n'a été réalisé.
