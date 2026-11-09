# A4 — Intégration vivante et démonstration ExFMD-CP

9 novembre 2026 — branche `a4-live-integration`, base A3/A3.4 **`bbd71ba`**. Aucun commit ni push effectué pendant A4.

## Résultat

**La chaîne CARLA → LiDAR/FusionDetector → ROS 2 → CPM R2 → Artery → F2MD A3 a fonctionné réellement sur Gyrovia, avec trois véhicules.** Le passage retenu produit **38 CPM applicatifs**, **38 copies ROS**, puis **52 réceptions radio natives**, toutes décodées, converties et contrôlées par F2MD. Les **52 décisions natives** correspondent exactement au recalcul par le véritable `CpmChecks` avec leurs horloges et paramètres observés. Zéro erreur technique et zéro conversion rejetée.

Le dashboard fonctionne en lecture autonome des résultats, sans CARLA/ROS ni interrogation de Docker. Il a été testé dans un navigateur avec les conteneurs ExFMD arrêtés. **14 occurrences de dépassement temporel demeurent** sur ce nouveau passage ; elles ne prouvent ni attaque ni faux positif.

Preuves principales : [passage conservé](a4-live-20261109-004/), [synthèse JSON](a4-live-20261109-004/summary.json), [validation A4](a4-live-20261109-004/attempt-01/validation-a4.json), [validation perception/CPM](a4-live-20261109-004/attempt-01/validation-01/validation.json).

## 1. État initial et composants utilisés

Le dépôt était sur `main`. `main` et `a3-temporal-plausibility` pointaient sur **`bbd71ba`**, commit contenant les développements A3/A3.4. La branche `a4-live-integration` a été créée depuis cet état ; les modifications locales de résultats et toutes les preuves non suivies ont été conservées. Aucun ancien fichier n'a été réinitialisé.

Les scripts A1 vivants et la bibliothèque F2MD calibrée A3 ont été réutilisés. Aucun composant C++ ni aucune image n'a été reconstruit. Le core A1 est `results/phase1/a1-e2e-20261106-161848/build/libartery_core.so`, SHA-256 **`e0d3531a331084f20cee7e3b4142981adf936edb0cd53b40f09a4798481d7a2b`**. Le F2MD exécuté est `results/phase3/calibration-20261108-190113/build/libartery_F2MD.so`, SHA-256 **`1d18655c07c943b0514d2453d139eb1b004329edcefe09a3bd05193d5557e229`**.

La [cartographie mémoire](a4-live-20261109-004/attempt-01/artery-memory-maps.txt) confirme leur chargement et l'absence du F2MD original concurrent. Les dépendances Vanetza, Artery, INET, TraCI et OMNeT++ restent celles de l'image Artery. CARLA utilise l'image locale UPHF 0.9.16 ; ROS 2 Humble utilise l'image ROS existante. [État initial des conteneurs et images](a4-live-20261109-004/containers-before.json).

Le service `CarlaPerceptionService` du véhicule source produit les CPM ; deux autres nœuds chargent `F2MD_CPService` en réception seule. Les CAM et la RSU du diagnostic A1 sont conservées. Aucun émetteur de replay n'est utilisé pendant ce passage vivant. Le tracker de production A3.3 est conservé ; la variante expérimentale A3.4 n'est pas activée.

La politique réelle est vérifiée dans chaque contrôle : accélération **3 m/s²**, décélération **4,5 m/s²**, direction **90°/s**, tolérance position/vitesse **3 m/s**, âge/intervalle maximum **5 s**, rétention **15 s**. Le contrôle A2 garde son initialisation native **4 + 0,1 = 4,1 m/s**. Kalman F2MD et distance/FoV restent non évaluables. Probabilité d'attaque **0**, type Genuine, mélanges et pseudonymes désactivés ; deux rôles `Genuine prob=0` sont observés. Ce rôle n'est pas un verdict de message sain.

## 2. Validation progressive mesurée

Le scénario effectue **75 pas de 50 ms**, soit **3,75 s nominales SUMO**, dans une configuration Artery limitée à 4 s. La portion de co-simulation mesurée par le processus ROS dure **89,33 s murales**, hors démarrage à froid et validations. Ce n'est pas une démonstration en temps réel.

| Étape | Preuve et résultat réel |
|---|---|
| CARLA / SUMO | Gyrovia, 3 véhicules, 225 positions, 75 correspondances de trames ; deux processus terminés avec le code 0 |
| Capteurs / Fusion | 74 callbacks LiDAR brut, 74 caméra, 74 instantanés Fusion et 148 états suivis |
| ROS 2 | 73 messages perception, 72 trames uniques ; 38 copies de CPM RAW |
| Construction R2 | 38 traces et marqueurs `CPM_A1_TX`, 38 charges entièrement décodées et valides avec Vanetza |
| Radio Artery / F2MD | 52 événements natifs `receive`, 26 par récepteur **161 et 233**, station source **88** |
| Décodage / conversion / contrôle | 52 / 52 / 52 ; 52 appels facility et 52 appels temporels, tous tracés |
| Recalcul indépendant de la simulation | Les 52 résultats de contrôle sont identiques au passage des mêmes octets dans le véritable `CpmChecks` |
| Dashboard | API LIVE observée pendant l'acquisition ; replay, sélection d'objet, trames et lecture testés dans Edge après arrêt des conteneurs |

Les **38 émissions sont applicatives**, constatées après remise à la pile Artery et par les captures ROS ; elles ne constituent pas un compteur de transmission MAC réussie. Les 52 réceptions natives concernent **26 charges distinctes**, chacune vue par les deux récepteurs. **12 des 38 charges émises n'ont pas de réception F2MD observée dans ce passage.** La cause précise à l'intérieur de la pile radio/DCC/MAC n'a pas été établie ; aucune livraison exhaustive ni aucun taux de fiabilité radio n'est revendiqué.

Les copies ROS ne sont jamais additionnées aux réceptions natives. Le topic RAW observé ici est `/simulator/vehicle2/cpm` ; son numéro de slot ne remplace pas l'identité ASN.1 de station. La filiation utilise les octets/SHA-256 et les identifiants réellement décodés.

Preuves : [exécution](a4-live-20261109-004/attempt-01/execution.json), [rapport ROS/capteurs](a4-live-20261109-004/attempt-01/report.json), [journal Artery](a4-live-20261109-004/attempt-01/artery.log), [événements F2MD](a4-live-20261109-004/attempt-01/f2md-events/), [contrôles reliés aux trames](a4-live-20261109-004/attempt-01/f2md-linked-checks.json).

### Horloges, IDs et valeurs

Les **76 couples perception/objet/CPM** conservent exactement les IDs ; piste **0 → acteur CARLA 2**, piste **1 → acteur 4**, sans changement d'association. Les **21 états prédits** observés sont distingués des mises à jour. L'écart de jointure CARLA/SUMO par même trame est **0 s** ; les deux origines temporelles restent distinctes. L'âge ASN.1 signé correspond à **110–210 ms**.

Erreur maximale source ENU → ASN.1 décodé : **0,004966 m** pour la position et **0,004934 m/s** pour la vitesse. Le recalcul depuis les intermédiaires géographiques diffère de moins de **7,2 × 10⁻¹⁰**. Dimensions, accélérations et IDs capteurs absents restent absents ; les diagnostics de modèle ne deviennent pas des confiances ASN.1.

Exemple réel, **trame 155, piste 0, station 88** :

| Champ | Source perception ENU | CPM décodé |
|---|---:|---:|
| X, m | −3,359005 | −3,36 |
| Y, m | −10,065771 | −10,07 |
| Z, m | 1,062436 | 1,06 |
| VX, m/s | −0,570727 | −0,57 |
| VY, m/s | −0,106441 | −0,11 |

Temps CARLA **68,815182503 s**, temps SUMO associé **0,2 s**, émission **0,310276337 s**, référence TAI **448538400310 ms**, delta objet **−110 ms**. L'époque Artery est celle du scénario de 2018, pas l'horloge murale de 2026. [Comparaisons CSV](a4-live-20261109-004/attempt-01/validation-01/object-comparisons.csv), [horloges par trame](a4-live-20261109-004/attempt-01/frame-times.jsonl).

### Résultats F2MD natifs

| Contrôle | `passed` | `anomaly` | `non_evaluable` |
|---|---:|---:|---:|
| Vitesse A2 | 100 | 0 | 4 |
| Ordre / fraîcheur | 104 | 0 | 0 |
| Cohérence de vitesse | 94 | 2 | 8 |
| Cohérence de direction | 88 | 8 | 8 |
| Cohérence position/vitesse | 92 | 4 | 8 |
| Distance/FoV | 0 | 0 | 52 |
| Kalman F2MD | 0 | 0 | 52 |

Les quatre contrôles temporels produisent **416 résultats : 378 succès de contrôle, 14 dépassements, 24 non évaluables**. Tous contrôles compris : **132 non évaluables**. Les 104 observations d'objet donnent **4 initialisations, 88 mises à jour, 12 rejets**. Dix messages reçus portent au moins un dépassement ; les 14 occurrences ne sont donc pas 14 messages indépendants. Tous les verdicts restent partiels, `complete=false`.

Ce passage vivant produit d'autres mesures et ne reçoit pas le même ensemble de paquets que le replay A3 précédent. **14 contre 24 ne démontre aucune amélioration du détecteur.** Sur les anciens octets et les mêmes paramètres/horloges, les 24 occurrences sont retrouvées exactement.

## 3. Dashboard et supports de réunion

Les trois anciennes applications de `dashboards/` dépendent de ROS, et certaines d'une carte Internet. Le serveur `scripts/results_server.py` et son dashboard de résultats ont fourni le modèle de serveur HTTP local et la présentation en panneaux. La version dédiée **`dashboards/a4/`** conserve cette approche, avec un lecteur de preuves spécifique **`scripts/a4_data.py`**. Les anciens dashboards/résultats sont préservés.

Le nouveau viewer utilise uniquement la bibliothèque standard Python et les ressources locales HTML/JS : aucun CDN, aucune requête Docker, aucun middleware requis en replay. Il affiche les composants selon leurs preuves observées, les trajectoires CARLA, les états ENU, le track/acteur/station/récepteurs, les dates, les compteurs séparés, les contrôles, les historiques et les événements. Les images caméra sont des captures ponctuelles, explicitement légendées. L'état d'un conteneur n'est jamais présenté comme la preuve d'un échange.

Le mode `--live` lit les fichiers en cours et tolère seulement une dernière ligne JSONL incomplète. À la fin, le bandeau devient **REPLAY**. L'API et l'interface n'inventent pas de valeurs lorsque les fichiers ne sont pas encore écrits ; notamment, le nombre de véhicules est indisponible avant l'archivage du CSV final.

Le test navigateur final sélectionne la piste 1 à la trame 163, retrouve la station 88, les récepteurs 161/233 et les 14 lignes de contrôle associées, puis fait avancer la lecture jusqu'à la trame 165. Aucun débordement horizontal ni erreur JavaScript n'est observé. [Résultat navigateur](a4-live-20261109-004/browser-check.json).

Supports exportables :

- [Capture du dashboard](a4-live-20261109-004/dashboard-a4.png) et [capture complète](a4-live-20261109-004/dashboard-a4-complet.png).
- [Figure de présentation PNG](a4-live-20261109-004/presentation-a4.png) et [version SVG](a4-live-20261109-004/presentation-a4.svg), issues des compteurs réels.
- [Caméra embarquée](a4-live-20261109-004/attempt-01/onboard.png), [vue extérieure](a4-live-20261109-004/attempt-01/overview.png), [données du dashboard](a4-live-20261109-004/dashboard-data.json).

## 4. Modifications et tests

**Aucun changement du tracker, de ses paramètres, des seuils ou du C++ F2MD.** Les modifications concernent le raccordement, la vérification de provenance et les outils de démonstration :

- `scripts/run_artery_diagnostic.py` : option explicite A4, chargement du F2MD validé, services source/récepteurs, réception seule, politique NED et absence d'attaque.
- `scripts/cpm/live_run.py`, `validate_live.py` : nouveau dossier phase4, sélection explicite des bibliothèques et vérification mémoire ; comportement A1 par défaut conservé.
- `scripts/cpm/runtime.py` : acceptation des seules différences LF/CRLF avec une archive source dont l'empreinte doit correspondre exactement au manifeste original. Tout autre changement et toute divergence du binaire restent refusés.
- `scripts/cpm/live_ros.sh`, `.gitattributes` : fins de ligne LF imposées pour le script Bash.
- `scripts/a4_*.py`, `scripts/run-a4-demo.ps1`, `dashboards/a4/`, `tests/cpm/test_a4_data.py` : orchestration, validations, replay, serveur, figures et tests.

Tests réussis : **28 tests Python A1/A3.3/A3.4**, **4 tests A4** (compteurs ROS/radio séparés, fin du live, lignes partielles, refus des sources modifiées ou archives falsifiées), **34 assertions C++ A1**, **26 A2**, **103 A3**, **132 calibration**. Les cas synthétiques incohérents des suites antérieures restent détectés ; aucun scénario d'attaque n'est lancé.

Régression enregistrée : **76 messages A2 et 150 évaluations de vitesse identiques**, **76 décisions natives A3 recalculées identiques, 24 occurrences conservées**. [Résultat](a4-live-20261109-004/recorded-regressions-01/summary.json). Les octets et SHA-256 d'entrée sont vérifiés ; seuls les préfixes de montage de l'index de test sont adaptés, sans modifier les index historiques.

Le wrapper PowerShell a été vérifié syntaxiquement et son mode Replay exécuté, y compris le réemploi d'un serveur déjà ouvert pour la même source. Les étapes du mode Live ont été réellement exécutées par l'orchestrateur puis, pour les vérifications ajoutées à la fin, séparément. **Le wrapper Live final complet n'a pas été relancé une seconde fois uniquement pour répéter toute la simulation.** Le test navigateur est une vérification optionnelle distincte ; il ne s'exécute pas automatiquement à chaque lancement Live.

### Échecs conservés

1. `a4-live-20261109-001` : arrêt initial sur les empreintes A3 devenues différentes après checkout CRLF. Pas de simulation.
2. `a4-live-20261109-002` : le script Bash CRLF échouait avant la sonde CARLA. Ce n'était pas un échec F2MD. Correction LF et règle Git ajoutées.
3. `a4-live-20261109-003` : CARLA disponible, mais refus de provenance du core A1, dont certaines sources archivées mêlaient LF/CRLF. L'archive exacte permet désormais de vérifier le contenu normalisé sans ignorer d'autres changements. Aucun contrôle F2MD exécuté lors de cet essai.
4. Un premier appel de test A1 a ciblé le montage `/repo` en lecture seule du builder ; ses sorties n'étaient pas conservées. Il a été refait avec un dossier nouveau accessible en écriture, et ses 34 assertions/artefacts ont été vérifiés. Le premier replay de régression supplémentaire échouait sur les chemins `/evidence` absents du conteneur runtime ; les chemins de la copie d'index ont été adaptés, les SHA-256 vérifiés, puis seul ce replay a été refait.
5. Premier essai navigateur : délai CDP de 15 s dépassé. Le suivant avec profil neuf, sans proxy et délai de 45 s passe. Un essai Chrome alternatif a rencontré l'ouverture transitoire du fichier de port ; cette attente a été rendue tolérante. La validation finale est celle d'Edge, dans `browser-final.log`.

Tous ces essais restent dans leurs dossiers/journaux. Ils ne sont pas comptés comme des validations réussies.

## 5. Lancer la démonstration

Depuis **`D:\ExFMD-CP`**, la version actuellement affichée est accessible à **<http://127.0.0.1:8766/>**. Le serveur de cette session reste ouvert ; les conteneurs ExFMD sont arrêtés.

Pour une réunion, le replay est le premier choix :

```powershell
cd D:\ExFMD-CP
.\scripts\run-a4-demo.ps1 -Mode Replay `
  -Source results/phase4/a4-live-20261109-004 -Port 8766 -Open
```

Ce mode n'appelle pas Docker. Il réutilise un viewer A4 déjà ouvert pour la même source, ou en démarre un. Un port occupé par un autre service n'est pas récupéré. La console fournit le PID et la commande `Stop-Process -Id <PID>` pour arrêter uniquement le viewer créé.

Pour une nouvelle acquisition complète, images et conteneurs préparés déjà présents, sur la branche A4, avec Docker disponible :

```powershell
# Port distinct du replay déjà affiché ; nouveau dossier horodaté automatique.
.\scripts\run-a4-demo.ps1 -Mode Live -Port 8767 -Open

# Même acquisition sans serveur graphique.
.\scripts\run-a4-demo.ps1 -Mode Live -NoDashboard
```

Le script vérifie branche, sources/binaire, conteneurs, ports CARLA et tests, démarre uniquement les composants nécessaires, attend CARLA et SUMO, exécute le scénario, décode/compare, rejoue les références, exporte figures/synthèse, puis rétablit l'état arrêté des conteneurs qu'il a démarrés. Le dashboard reste ouvert pour la présentation. Prévoir plusieurs minutes de démarrage à froid ; le rendu logiciel observé et le temps mural ne permettent pas de promettre du temps réel.

Pour tester séparément le lecteur et le navigateur :

```powershell
python -m unittest discover -s tests/cpm -p test_a4_data.py -v
python scripts/a4_browser_check.py --source results/phase4/a4-live-20261109-004 --port 8766
```

Cette dernière commande emploie Edge et le module `websocket-client` déjà disponible sur ce PC ; elle ouvre uniquement un profil de test neuf. Ils ne sont pas requis pour le viewer ni pour le replay des données.

## 6. Limites et préservation

La publication capteur n'est toujours pas exhaustive : **74 trames Fusion, 72 trames perception uniques**. Les trames **167 et 226** ne figurent pas dans les messages perception ; la trame **166** apparaît deux fois. Les 38 CPM émis restent tous reliés à une perception complète. Le mécanisme de publication lié au callback LiDAR brut ne garantit pas une publication par trame Fusion ; il n'a pas été remanié pour A4.

Les centroïdes visibles et vitesses suivies ne sont pas une vérité physique indépendante ; les incertitudes du modèle restent non calibrées. Les diagnostics `estimation_quality` sont locaux/JSON, pas des champs ETSI ni des confiances reçues par F2MD. Aucun FPR/TPR, précision physique ou conformité normative complète n'est revendiqué. Les décisions ne sont pas publiées vers ROS : le dashboard lit les traces natives séparément. Une démonstration longue, une reprise automatique après panne et un benchmark de charge n'ont pas été validés.

**2 801 fichiers antérieurs et sources de production sont vérifiés inchangés**, y compris A1/A2/A3 et les anciens résultats. Les images originales gardent leurs identifiants. L'état des 13 conteneurs existants est restauré ; postgres/pgadmin de l'autre projet restent actifs. Aucun nouveau conteneur n'a été créé pour A4. [Préservation après scénario](a4-live-20261109-004/preservation-after.json), [vérification finale](a4-live-20261109-004/preservation-final.json), [empreintes de l'outillage final](a4-live-20261109-004/tooling-hashes.json), [inventaire des preuves](a4-live-20261109-004/evidence-sha256.json).

**Décision : démonstration fonctionnelle de bout en bout acquise pour ce scénario court, avec repli replay testé.** La suite utile est de qualifier la livraison radio et la publication par trame, puis d'acquérir les données géométriques/observations nécessaires à la stabilité du point suivi. Kalman F2MD et distance/FoV restent désactivés. Aucun scénario d'attaque, aucune reconstruction d'image, aucun commit ni push.
