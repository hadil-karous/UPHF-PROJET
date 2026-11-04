> Historique du premier essai. Les images ROS/Artery ont depuis ?t? ajout?es et test?es. Voir [README_runtime.md](README_runtime.md) pour le nouvel ?tat v?rifi?.

# Relancer Gyrovia depuis PowerShell

Exécution vérifiée le 4 novembre 2026. Le conteneur existant `exfmd-carla` est conservé, sans reconstruction de CARLA. Les disques Docker ont été localisés sur D:\DOCKER_DATA\DockerDesktopWSL (VHDX de données et système). Aucun autre conteneur n'a été modifié.

## Commandes testées et relance

Depuis D:\ExFMD-CP :

```powershell
# Si CARLA a été arrêté :
docker start exfmd-carla
# Test CARLA seul : véhicule physique, caméra fixe, LiDAR, GNSS et IMU.
powershell -ExecutionPolicy Bypass -File .\scripts\start-gyrovia.ps1
# Arrêt anticipé depuis un second terminal, avec nettoyage des acteurs du test :
powershell -ExecutionPolicy Bypass -File .\scripts\stop-gyrovia.ps1
# Dépendances SUMO : déjà installées dans ce conteneur, à refaire s'il est recréé.
powershell -ExecutionPolicy Bypass -File .\scripts\setup-sumo.ps1
# Test de l'intégration CARLA–SUMO réelle du dépôt :
powershell -ExecutionPolicy Bypass -File .\scripts\start-cosimulation.ps1
```

Ne pas lancer les deux validations simultanément. Elles refusent un monde déjà synchrone. CARLA reste actif après leur fin. Le test CARLA est borné à 50 pas de 50 ms : un pilotage tout droit plus long sort de cette portion de piste. Il vérifie un déplacement supérieur à 1 m, une vitesse supérieure à 0,5 m/s et une variation verticale inférieure à 0,5 m. Le test SUMO fait 60 pas et vérifie le déplacement d'un acteur associé. Il ne valide pas la physique du véhicule CARLA, dont les poses sont imposées par SUMO, ni l'alignement de toute la carte.

Les résultats sont copiés dans `results/scenario2-carla/<date>/` et `results/cosimulation/<date>/`. La première synchronisation validée est dans `results/scenario2-cosimulation/`. Les sorties intermédiaires et dépendances du conteneur sont sous `/tmp/exfmd-*`, sur le disque Docker D:. Les scripts ne téléchargent pas d'image Docker.

## Résultats vérifiés

- CARLA seul : `results/scenario2-carla/20261104-183524/`, image `gyrovia_hero.png`, positions et vitesses `positions.csv`, nuage brut `lidar.ply`, mesures `report.json`.
- SUMO seul : `results/scenario2-sumo/`, traces `fcd.xml`, `summary.xml` et journal `run.log` ; 10 secondes simulées, deux véhicules insérés.
- CARLA–SUMO : `results/scenario2-cosimulation/`, 60 associations échantillonnées, 9,76 m de déplacement.
- Ancien diagnostic `20261104-183231` : conservé et marqué invalide car le véhicule quitte la piste puis chute.

## Limites et audit

`main.py` orchestre trois véhicules avec ROS 2 et SUMO Town04 et recharge une carte CARLA configurée. `main1.py` en est une variante incomplète : `client` et `world` ne sont pas initialisés. `main_uphf.py` est le point d'entrée adapté à Gyrovia, car il conserve le monde actif et utilise le réseau UPHF.

Corrections ciblées dans `main_uphf.py` : chemins relatifs au dépôt, suppression des ticks CARLA en double, intervalle de calcul des vitesses, configuration par défaut `cosimulation/configs/gyrovia.yaml`, choix du véhicule SUMO `0` effectivement présent. Cette entrée ROS n'a pas été exécutée, ROS 2 étant absent. Son initialisation et sa gestion des exceptions restent à durcir avant une longue exécution.

La configuration `configs/simulation.yaml` attendue par les anciens scripts manque. Le réseau UPHF existe, mais ses routes n'ont aucun `hero`, `hero1`, `hero2`. Le fichier `hero.rou.xml` contient en réalité un rerouter, pas un véhicule hero. Aucune RSU V2X n'a été exécutée : la caméra fixe de validation n'est pas une RSU radio. Le scénario 2 complet reste donc incomplet.

Dépendances installées de façon isolée : eclipse-sumo 1.19.0, NumPy 1.26.4, PyYAML 6.0.2, lxml 5.3.0, environ 96 Mo téléchargés. Client CARLA 0.9.16 déjà présent réutilisé. ROS 2/rclpy, OMNeT++, Artery, Vanetza et F2MD ne sont pas disponibles dans l'environnement testé. WSL ne contient que docker-desktop ; aucune distribution Ubuntu de développement n'a été trouvée. Aucun SUMO ou ros2 n'a été trouvé sur le PATH Windows.

Les requêtes Docker Hub `/v2/repositories/sarra13ba/{artery-ros,f2md-cpm,perception-bridge}/tags` ont chacune répondu HTTP 404. Images publiques indisponibles sous ces noms ou privées ; aucun téléchargement tenté. Pour poursuivre la chaîne complète, il faut les sources/builds compatibles ou l'accès aux images et tags exacts. Le dépôt contient des services Artery C++ à intégrer, pas une installation compilée complète ni un déploiement F2MD prêt à exécuter.

ROS requiert les interfaces standard sensor_msgs/nav_msgs/geometry_msgs/std_msgs et les interfaces ETSI `etsi_its_cam_msgs` et `etsi_its_cpm_ts_msgs`. Les bridges CAM souscrivent à `/its/cam_received`. Le générateur CPM publie sur `/its/cpm/v1000000001` etc., tandis que VehicleAgent publie la perception sur `/carla/hero/perceived_objects`, pas `/perception/objects`. La présence des topics `/its/cpm_received` et `/v2x_alert` n'a pas été démontrée. Aucun topic, format ou débit ROS n'a été validé.

Les bridges JSON de perception et les services Artery contiennent encore des chemins `/home/syfra/artery_fresh/...` ; ils devront partager un volume et des chemins explicitement configurés. Le client PointPillars attend un serveur TCP sur 9999, absent. Les bridges multi_shm nécessitent un partage de mémoire accessible aux processus concernés. Les configurations Artery historiques ciblent également Town01/Town04 et ne constituent pas un scénario RSU Gyrovia validé.

Réseau actuel : CARLA RPC/streaming 2000–2002, Traffic Manager 8000. Ces ports sont déjà publiés par le conteneur fonctionnel. TraCI utilise un port local géré au lancement dans le même conteneur. Pour une future architecture multi-conteneurs, `127.0.0.1` désigne chaque conteneur et devra être remplacé par un nom réseau approprié ; DDS ROS exige une configuration de découverte adaptée à Docker Desktop. Aucun Compose artificiel n'a été ajouté : les deux composants exécutés partagent ici le conteneur existant.

Les tableaux de bord du dépôt sont des serveurs Python/ROS, pas des dashboards Grafana fournis prêts à charger. Grafana n'est pas présent dans les conteneurs inspectés ; aucune URL Grafana opérationnelle. Les autres projets PostgreSQL/pgAdmin ont été conservés.

Le rendu est lent : le test CARLA atteint un facteur temps réel d'environ 0,0605 (2,45 secondes simulées pour 40,51 secondes murales incluant la préparation). Cette mesure ne suffit pas à attribuer le ralentissement au GPU. L'image obtenue montre le véhicule sur la piste. Les callbacks GNSS/IMU sont comptés ; leurs valeurs brutes ne sont pas exportées. Le nuage LiDAR est une donnée de capteur, aucune détection FusionDetector ou alerte F2MD n'est revendiquée.
