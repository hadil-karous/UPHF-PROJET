> Historique du premier essai. Les images ROS/Artery ont depuis ?t? ajout?es et test?es. Voir [RAPPORT_RUNTIME.md](RAPPORT_RUNTIME.md) pour le nouvel ?tat v?rifi?.

# Rapport d'exécution — 4 novembre 2026

| Composant | Statut | Commande | Résultat |
|---|---|---|---|
| CARLA 0.9.16 | Testé | scripts/start-gyrovia.ps1 | Client connecté, paramètres restaurés après test |
| Gyrovia | Testé, scénario 2 partiel | scripts/start-gyrovia.ps1 | 5,79 m, 5,11 m/s max, image et capteurs ; aucune RSU V2X |
| SUMO 1.19 | Testé seul et couplé | scripts/start-cosimulation.ps1 | 10 s seul ; 60 pas couplés, déplacement 9,76 m |
| ROS 2 | Absent de l'environnement testé | Non disponible | Aucun message validé |
| Artery / OMNeT++ / Vanetza | Absents | Non disponible | Services sources seulement, image annoncée HTTP 404 |
| CAM / CPM | Non testés | Non disponible | Interfaces ETSI et chaîne ROS/V2X manquantes |
| F2MD | Non disponible | Non disponible | Aucune alerte mesurée |
| Grafana | Non disponible | Non disponible | Aucun dashboard ni URL validés |

Éléments créés : scripts de validation CARLA et synchronisation, scripts PowerShell de lancement/arrêt/préparation SUMO, configuration Gyrovia, README_execution.md, ce rapport et les résultats par composant. Seul fichier suivi préexistant modifié : cosimulation/main_uphf.py. Le dossier demo préexistant non suivi a été préservé.

Preuves : scenario2-carla/20261104-183524/report.json et positions.csv, gyrovia_hero.png, lidar.ply ; scenario2-sumo/fcd.xml, summary.xml, run.log ; scenario2-cosimulation/report.json et positions.csv. Le premier parcours en ligne droite est conservé comme diagnostic échoué.

Le véhicule sélectionné explicitement, la physique active, le frein à main relâché et les ticks de 50 ms ont permis une accélération mesurée après environ 0,8 s simulée. La cause exacte de l'immobilité dans l'ancienne démonstration n'est pas établie : elle sélectionne arbitrairement le premier blueprint et observe le temps mural sans maîtriser le pas simulé. Le nouveau test démontre le mouvement sans imposer les positions. Un trajet autonome prolongé et la chaîne complète avec RSU restent à valider.

Les dépendances V2X manquantes et les images privées/introuvables empêchent la suite complète ; elles n'ont pas été remplacées par des messages synthétiques. Voir ../README_execution.md pour relancer et pour les dépendances, chemins et connexions à résoudre.
