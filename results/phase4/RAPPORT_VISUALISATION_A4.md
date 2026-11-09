# A4 — Démonstration visuelle CARLA et F2MD

9 novembre 2026 — branche `a4-live-integration`. Aucun commit ni push.

**La visualisation a été exécutée et vérifiée : images CARLA animées à gauche, perceptions et contrôles F2MD à droite. L'interface est ouverte sur <http://127.0.0.1:8767/> et reste en replay animé après la simulation.**

Nouvelle acquisition : [a4-visual-20261109-01](a4-visual-20261109-01/). Les rapports et preuves A1/A2/A3/A4 précédents sont préservés.

## Ce qui empêchait l'affichage

Le serveur CARLA existant est un programme Linux dans Docker, lancé avec `RENDER_MODE=offscreen` et `-RenderOffScreen`. Il n'a ni variable `DISPLAY`/`WAYLAND_DISPLAY` ni montage d'affichage vers Windows. Le lanceur place initialement le spectator à 180 m ; surtout, le précédent diagnostic ne sauvegardait qu'une image par caméra. Il n'existait donc pas de vidéo à lire dans l'ancien dashboard.

Une fenêtre CARLA native Windows n'est pas fournie par cette configuration. Retirer simplement `-RenderOffScreen` ne crée pas une connexion graphique vers le bureau Windows. La solution retenue conserve le serveur et ses images : **deux caméras RGB CARLA exportent leurs trames vers le navigateur**. Aucun X Server, serveur Windows CARLA ou transfert de fenêtre supplémentaire n'a été installé.

`no_rendering_mode=false` est vérifié avant le scénario : **offscreen ne signifie pas absence de rendu**. Le conteneur demande l'accès GPU ; Windows dispose d'une NVIDIA T1000 8 Go et d'un circuit Intel UHD 770. Un avertissement `lavapipe` apparaît au lancement. Cet avertissement seul ne prouve pas quel périphérique UE4 sélectionne : contrairement à l'hypothèse initiale de rendu exclusivement logiciel, **l'accélération GPU effective n'est pas établie par ces vérifications**. Le journal UE4 recherché n'est pas disponible à son emplacement habituel. La production des images RGB, elle, est directement validée. [Configuration relevée](a4-visual-20261109-01/render-configuration.json), [lanceur du conteneur](a4-visual-20261109-01/carla-launch.sh).

## Affichage réellement ajouté

- Vue générale en perspective : caméra spectator suivant le centre des véhicules, altitude 25 m, inclinaison −70°, champ horizontal 75°.
- Vue embarquée attachée à l'ego ; sélection depuis la même interface.
- Images **960 × 540**, demandées tous les 100 ms simulés, sauvegardées par `carla.Image.save_to_disk`. Le navigateur affiche cette séquence PNG ; aucune image intermédiaire n'est interpolée ou fabriquée.
- En LIVE, la lecture suit les nouvelles trames disponibles. En REPLAY, elle boucle automatiquement, avec **Play/Pause**, curseur, **0,25× / 0,5× / 1× / 2×**, choix de caméra et d'objet.
- Le lecteur visuel retient les trames communes aux deux caméras et à FusionDetector. Les positions/vitesses correspondent à la même trame que l'image sélectionnée. Les contrôles affichés sont les derniers réellement reçus avant l'instant SUMO correspondant ; leur trame source est indiquée séparément.
- Les compteurs représentent le **total du passage**, clairement légendé. Les copies ROS ne deviennent jamais des réceptions radio F2MD. Le mode LIVE/REPLAY reste explicite.

La séquence est une capture du rendu 3D de Gyrovia, avec ses acteurs simulés. La carte XY complémentaire est une visualisation des positions ; elle n'est pas utilisée pour fabriquer les images caméra.

## Vérifications obligatoires réalisées

| Vérification | Résultat observé |
|---|---|
| Vrais véhicules visibles | Trois véhicules observés dans les images ; au moins deux entièrement dans le champ aux deux extrémités de la séquence |
| Mouvement de ces deux véhicules | `hero` / acteur 3 : **4,40 m** ; `hero1` / acteur 4 : **6,14 m** entre les images initiale et finale |
| Nouvelles images en LIVE | Premier test navigateur : RGB **146 → 150**, captures disponibles **6 → 10**, contrôles natifs **6 → 8** |
| LIVE avec lecteur final | Deuxième test : RGB **210 → 214**, images disponibles **70 → 74** |
| Images sauvegardées | **74 images valides : 37 générales + 37 embarquées** ; toutes décodées, non vides et jointes aux états CARLA de la même trame |
| Caméra/perception synchronisées | Exemple navigateur final : **RGB 212 = perception 212** ; mêmes temps caméra/états vérifiés sur les 74 images |
| Play/Pause | Curseur stable pendant la pause ; reprise vérifiée |
| Vitesse de lecture | Sur environ 0,7 s de test : **2 pas à 0,25× contre 12 pas à 2×** |
| Caméras / objets / navigation | Changement général ↔ embarqué, piste 1 et curseur testés ; pas d'erreur JavaScript ni de débordement horizontal |
| Arrêt et relance | `stop-visual-demo.ps1` exécuté, puis relance effective du mode Replay sur le même port |

La visibilité a aussi été contrôlée par projection des boîtes CARLA dans les images avec les transformations réelles des capteurs. Les images initiale, finale et les captures du navigateur ont été inspectées visuellement. Le troisième véhicule est partiellement recadré en fin de passage ; aucune visibilité intégrale des trois véhicules sur toute la séquence n'est revendiquée.

Preuves : [validation des images et mouvements](a4-visual-20261109-01/visual-validation.json), [premier test LIVE](a4-visual-20261109-01/browser-live-initial.json), [LIVE final](a4-visual-20261109-01/browser-live.json), [tests REPLAY](a4-visual-20261109-01/browser-replay.json), [messages caméra](a4-visual-20261109-01/attempt-01/camera-frames.jsonl), [états CARLA/SUMO explicitement associés](a4-visual-20261109-01/attempt-01/visual-states.jsonl).

## Chaîne technique conservée

Le nouveau scénario compte **3 véhicules**, **74 trames Fusion**, **225 positions** et **38 CPM R2**, tous capturés dans ROS puis décodés. F2MD reçoit, décode et contrôle **52 événements radio natifs**, dont les décisions concordent exactement avec le recalcul par `CpmChecks`. Zéro erreur technique, zéro conversion rejetée. [Validation du passage](a4-visual-20261109-01/attempt-01/validation-a4.json).

Il reste **10 occurrences de dépassement temporel** dans cette acquisition. Ce sont de nouvelles mesures et un nouveau calendrier de publication ; leur nombre ne se compare pas directement aux 14 de l'acquisition A4 précédente ni aux 24 du corpus A3. Aucun seuil ou contrôle F2MD n'a changé. Les contrôles restent partiels ; Kalman F2MD et distance/FoV sont désactivés. Aucun scénario d'attaque.

Les suites **28 tests Python**, **34 assertions C++ A1**, **26 A2**, **103 A3**, **132 calibration** ont été exécutées pendant ce lancement. Les **6 tests du lecteur de données**, dont les deux nouveaux tests caméra/association, passent également. La régression retrouve les **76 messages / 150 contrôles de vitesse A2** et les **76 décisions A3 / 24 dépassements historiques** identiques. Le binaire F2MD calibré est réutilisé sans reconstruction. [Régressions enregistrées](a4-visual-20261109-01/recorded-regressions-01/summary.json), [tests du lecteur](a4-visual-20261109-01/visual-unit-tests-final.log).

Modifications : capture optionnelle `scripts/visual_capture.py` dans le lanceur intégré ; option `--visual` des lanceurs ; lecture des images/états dans `a4_data.py`, routes PNG dans `a4_dashboard.py`, interface dédiée `dashboards/a4/visual.{html,js}`, scripts de démarrage/arrêt et de vérification. **Le tracker de production et le C++ F2MD sont inchangés.** Les vérifications visuelles finales ont été exécutées séparément, puis intégrées au lanceur pour les prochaines acquisitions ; aucune nouvelle simulation n'a été refaite pour répéter ces seules vérifications.

## Commandes de démonstration

Sur ce PC, ouvrir maintenant **<http://127.0.0.1:8767/>**. Le replay animé reste ouvert ; CARLA et les autres conteneurs ExFMD sont arrêtés.

```powershell
cd D:\ExFMD-CP

# Ouvrir / réutiliser la démonstration enregistrée, sans Docker ni CARLA.
.\scripts\run-visual-demo.ps1 -Mode Replay

# Nouvelle acquisition réelle ; démarrer après avoir arrêté le viewer existant.
.\scripts\stop-visual-demo.ps1
.\scripts\run-visual-demo.ps1 -Mode Live

# Arrêter uniquement le viewer et le scénario lancés par ce script.
.\scripts\stop-visual-demo.ps1
```

Pour choisir explicitement les résultats conservés :

```powershell
.\scripts\run-visual-demo.ps1 -Mode Replay `
  -Source results/phase4/a4-visual-20261109-01 -Port 8767
```

Le mode Live ouvre immédiatement le navigateur, puis prépare la chaîne en arrière-plan. Il crée un nouveau dossier et refuse de remplacer un dossier existant. À la fin, il arrête les conteneurs qu'il a démarrés et laisse le viewer en replay. L'arrêt vérifie les identifiants et le dossier de sortie des processus avant de signaler le scénario. Le mode Replay n'appelle pas Docker et relit uniquement les images/données sauvegardées.

Prévoir plusieurs minutes pour un démarrage Live à froid. La portion co-simulation dure **128,91 s murales pour 3,75 s simulées**, hors préparation : le LIVE ne fonctionne pas à 10 images/s murales sur ce passage. Le replay utilise les temps simulés et offre une lecture plus régulière. Il ne doit pas être présenté comme une simulation encore active.

## Captures et préservation

- [Image CARLA initiale](a4-visual-20261109-01/captures/carla-debut.png) / [image finale](a4-visual-20261109-01/captures/carla-fin.png).
- [Interface pendant le LIVE](a4-visual-20261109-01/captures/dashboard-live.png).
- [Interface et contrôles en REPLAY](a4-visual-20261109-01/captures/dashboard-replay.png).

**3 249 fichiers antérieurs/sources sont vérifiés inchangés**, incluant les preuves A1/A2/A3 et le manifeste des preuves A4 précédentes. Images Docker conservées, aucune reconstruction, aucun commit ni push. Les conteneurs existants retrouvent leur état initial ; postgres/pgadmin restent actifs. Le viewer visuel reste ouvert pour l'utilisateur. [Préservation](a4-visual-20261109-01/preservation-final.json).

Les résidus de perception et covariances ne sont toujours pas une précision physique calibrée. La démonstration valide la circulation rendue, le raccordement des données et les commandes de visualisation ; elle ne valide ni FPR/TPR, ni livraison radio exhaustive, ni accélération GPU.
