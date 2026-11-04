# ExFMD-CP — démonstration locale avec résultats visibles

Les trois images existantes sont réutilisées : CARLA 0.9.16, exfmd-ros:1.0 (Humble) et exfmd-artery:1.0 (OMNeT++ **5.6.2 réellement observé**, pas 5.7.1). CARLA n'a pas été réinstallé. Toutes les nouvelles dépendances et sorties sont sur D:, directement dans le dépôt ou dans les VHDX Docker déjà situés sur D:.

## Ouvrir les résultats

URL Windows : **http://127.0.0.1:8765/dashboard/**

```powershell
cd D:\ExFMD-CP
powershell -ExecutionPolicy Bypass -File .\scripts\start-dashboard.ps1 -Open
```

Le dashboard affiche le dernier test terminé : captures, trajectoire par véhicule, vitesse, erreur spatiale, nuage LiDAR manipulable, compteurs ROS, statistiques radio RSU et résultats du test F2MD séparé. Les conteneurs sont interrogés séparément. « Running » signifie uniquement que le conteneur tourne : le bandeau indique clairement que les mesures sont enregistrées. Actualiser après la fin d'un scénario pour voir ses résultats. Aucun flux 3D Unreal en direct n'est configuré. Le navigateur a été ouvert ; disponibilité HTTP et syntaxe JavaScript vérifiées, sans automatisation de navigateur disponible pour tester tous les contrôles.

## Relancer après redémarrage

```powershell
# Un véhicule + RSU, scénario borné :
powershell -ExecutionPolicy Bypass -File .\scripts\start-exfmd.ps1 -Vehicles 1 -OpenDashboard
# Variante validée à trois véhicules :
powershell -ExecutionPolicy Bypass -File .\scripts\start-exfmd.ps1 -Vehicles 3 -OpenDashboard
# État actuel, distinct des résultats enregistrés :
powershell -ExecutionPolicy Bypass -File .\scripts\status-exfmd.ps1
# Arrêt du projet ROS/Artery, conservation de CARLA et des autres projets :
powershell -ExecutionPolicy Bypass -File .\scripts\stop-exfmd.ps1
# Ajouter -StopDashboard pour arrêter aussi le serveur de résultats.
```

Docker Desktop doit être démarré. Le conteneur CARLA existant est redémarré si nécessaire. La première connexion peut prendre davantage de temps pendant le chargement de CARLA. Attendre que le serveur soit prêt avant de relancer si les logs indiquent un délai RPC dépassé.

`docker/compose.runtime.yaml` gère seulement exfmd-ros et exfmd-artery. CARLA existant est connecté au réseau exfmd-runtime sans remplacement. ROS partage le réseau et l'IPC d'Artery : les services C++ envoient leurs UDP à 127.0.0.1 et lisent /dev/shm/agent_N et /dev/shm/perceived_0. ROS_DOMAIN_ID=42, rmw_fastrtps_cpp. Le client CARLA se connecte à exfmd-carla:2000. SUMO est lancé par Artery avec deux clients TraCI sur 8813 ; Artery a l'ordre 1, le synchroniseur Python l'ordre 2. Aucun port UDP supplémentaire n'est exposé à Windows.

Les dépendances SUMO 1.19 existantes ont été conservées sur `results/runtime-audit/deps/`. Le wheel CARLA déjà fourni dans l'image a été copié dans `results/runtime-audit/`. Le lanceur prépare le client dans /tmp/exfmd-python si nécessaire. Matplotlib et ses dépendances sont conservés dans `results/runtime-audit/plot-deps/`. Ces dossiers sont nécessaires pour une relance après recréation des conteneurs ; ne pas les supprimer. Aucun téléchargement d'image ni recompilation n'est nécessaire.

Chaque lancement crée `results/integrated/run-<date>/` et y conserve `artery.log`, `ros.log`, positions.csv, report.json, images, nuage, mesures PNG/SVG, configurations et scalaires OMNeT++. Les deux anciens scripts CARLA seul et CARLA–SUMO seul sont conservés. Ne pas exécuter plusieurs scénarios simultanément sur ce serveur CARLA.

## Nature exacte du scénario

Il s'agit d'une **variante de diagnostic explicite**, pas d'une reproduction certifiée du scénario original de Sarra. Elle utilise le réseau Gyrovia et la première route du dépôt, les services CarlaCaService, CamUdpExportService, CarlaPerceptionService, RsuCaService compilés dans l'image, et le véritable synchroniseur CARLA–SUMO. Un vType Tesla, une limitation à 4 m/s, un à trois véhicules, une RSU proche de la route et les chemins adaptés sont déclarés dans les fichiers générés et consultables.

Le scénario original F2MD_Highway_CPM ne démarre pas tel quel : racines NED incorrectes, chemins /home/syfra, ligne INI concaténée, répertoire de résultats manquant et référence à route2 sans définition. Les traces et originaux sont conservés dans `results/runtime-audit/`. Le gestionnaire compilé crée node0/node1/node2 : les paramètres doivent utiliser node*, pas node[*]. SUMO fourni nativement dans l'image Artery est 1.12 ; la variante utilise le 1.19 déjà validé.

## Preuves principales

`results/integrated/demo-003/` :

- 3 véhicules, 75 pas, 225 positions ; hero parcourt 4,719 m ; vitesse maximale sur tous les véhicules 4,000 m/s.
- Erreur spatiale maximale CARLA vs pose SUMO convertie : 1,97e-6 m. Cette valeur ne prouve pas l'alignement de toute la carte ni un fonctionnement en temps réel. La physique des véhicules est désactivée par le synchroniseur ; leur déplacement est commandé par SUMO.
- 74 images ROS et 74 messages LiDAR ROS reçus ; captures extérieures/embarquées et nuage PLY exportés.
- FusionDetector suit 2 autres voitures. Le code utilise les identifiants et tags sémantiques CARLA pour regrouper les points, puis un suivi Kalman. Ce résultat n'est pas une inférence PointPillars ; son serveur TCP 9999 est absent. Le score 1.0 est fixé dans le code, pas une confiance calibrée.
- CAM décodés reçus par ROS : 37 + 38 + 38 = 113. CPM : 38 paquets bruts reçus sur /simulator/vehicle2/cpm. Ces CPM sont émis par CarlaPerceptionService à partir des objets réellement détectés. Le bridge fourni exporte des octets ; aucun décodage ROS ETSI du contenu CPM ni réception radio CPM dans le détecteur historique n'est validé par ce compteur.
- RSU : 116 CAM reçus, 39 émis selon omnet-results/General-#0.sca. C'est une preuve radio distincte des exports UDP.

Le créateur de Router attribue les ports RAW par ordre de création : avec la RSU, les slots ne correspondent pas strictement à vehicle1/vehicle2/vehicle3. Le quatrième slot RAW n'est pas écouté par les bridges fournis ; les trois stations CAM sont néanmoins observées via les ports JSON 9001–9003. Les noms réels sont /its/cam/v88, v161 et v234 dans ce test, pas /its/cam_received. La perception est sur /carla/hero/perceived_objects. Aucun /v2x_alert n'est validé.

Les fréquences affichées dans le dashboard sont calculées en temps mural à partir des réceptions. Les timers VehicleAgent utilisent le temps mural et peuvent republier le dernier état alors que le simulateur est lent ; /clock et use_sim_time ne sont pas configurés. Les images sont des captures, pas une vidéo en direct. Le nuage PLY correspond à un seul échantillon réel.

## F2MD : deux diagnostics séparés

`results/f2md-probe/` : un récepteur F2MD historique initialise sa facility, mais aucun enregistrement CPM utile ni alerte n'est produit avec les CPM r2 de CarlaPerceptionService. Les sources montrent un générateur asn1::r2::Cpm et un détecteur utilisant asn1::Cpm : l'incompatibilité de génération/décodage est une piste concrète, pas un pont corrigé et validé.

`results/f2md-native-probe/` : 3 secondes de simulation Artery autonome sur la route Gyrovia, avec FrontRadar et les CPM historiques de F2MD. Les CAM utilisent le dernier état réel enregistré dans la mémoire partagée ; ce diagnostic ne représente pas un nouveau couplage CARLA. 114 enregistrements CPM reçus, 76 marqués checkfailed, 38 fichiers alert_*.json. Le nom de fichier ne contient pas l'identifiant du récepteur : des écritures au même instant peuvent se remplacer, donc nombre de fichiers et nombre d'événements diffèrent. Le scénario est Genuine sans attaque injectée : ces alertes ne démontrent aucune précision de détection et nécessitent une analyse des faux positifs et des hypothèses de coordonnées.

Relance des diagnostics uniquement lorsque la simulation intégrée est arrêtée :

```powershell
docker exec exfmd-artery bash -lc 'ulimit -c 0; python3 /repo/scripts/probe_f2md.py'
docker exec exfmd-artery bash -lc 'ulimit -c 0; python3 /repo/scripts/probe_f2md_native.py'
```

Leur répertoire fixe est destiné au diagnostic existant ; archiver ces sorties avant une nouvelle exécution si vous souhaitez conserver chaque version. Le lancement principal utilise toujours un nouveau répertoire.

Pour compléter ExFMD-CP : adapter et valider le décodage CPM r2 vers la facility F2MD, définir un contrat de coordonnées et de temps commun, corriger l'identité et l'horodatage des sorties, ajouter un bridge d'alertes ROS puis tester des scénarios avec vérité terrain. Aucun Grafana n'est installé ; le dashboard local satisfait la consultation des résultats disponibles.
