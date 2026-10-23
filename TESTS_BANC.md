# Tests physiques à réaliser sur le banc

Tests à faire après les modifications de la branche `reliability-improvements`.
Chaque section correspond à une tâche de `IRLab_modifications.md` et à un commit :
en cas de problème, on peut revenir en arrière tâche par tâche.

Cocher chaque test une fois validé, et noter le résultat en cas d'échec.

> **Spectromètre reporté.** Pour cette campagne (v1.0), le serveur spectro est désactivé
> (`disabled_servers` dans `config/servers.yaml`) : le shell ne le contacte pas et l'affiche
> `DISABLED`. Les tests marqués *(reporté : spectro désactivé)* seront faits plus tard,
> après l'avoir retiré de cette liste.

---

## Tâche 1 : verrou d'accès au port série (commit `e689b71`)

Préparation : serveur moteurs démarré, shell IPython ouvert sur **deux PC différents**.

- [ ] **Lectures pendant un mouvement.** Depuis le PC A, lancer un long `mv` sur un moteur.
  Pendant le mouvement, faire plusieurs `wm()` depuis le PC B.
  *Attendu :* positions cohérentes, aucune erreur, le `mv` du PC A se termine normalement.
- [ ] **Second mouvement refusé.** Pendant un long `mv` du PC A, lancer un `mv` du **même** moteur depuis le PC B.
  *Attendu :* refus immédiat « motor busy » (HTTP 409) ; le premier mouvement n'est pas perturbé.
  *(Avant la tâche 3, le client peut afficher ce refus comme une erreur générique.)*
- [ ] **Init / control refusés pendant un mouvement.** Pendant un long `mv`, lancer `control(moteur)` depuis l'autre PC.
  *Attendu :* refus « motor busy ».
- [ ] **Deux moteurs du même PS90.** Lancer un `mv` du moteur 1 depuis le PC A et un `mv` du moteur 2 (même contrôleur) depuis le PC B.
  *Attendu :* les deux mouvements aboutissent aux bonnes positions.

Remarques / résultats :

---

## Tâche 2 : lecture série robuste

Préparation : serveur moteurs démarré, shell IPython ouvert.

- [ ] **Réglages de communication du PS90** (d'après le manuel du PS90+, à confirmer sur l'ancien PS90) :
  - fin de réponse : `CR` par défaut (`COMEND=0`). Le code gère `CR` et `CR+LF`, **pas `LF` seul** (`COMEND=2`) : dans ce cas toutes les lectures échoueraient en timeout. Le plus simple pour le voir : activer `log_serial: true` (tâche 12) et regarder la fin des réponses (`<< b'1234\r'`) ;
  - délai entre commandes : le manuel indique 20 à 40 ms de traitement ; le code attend 0,05 s (réglable par contrôleur avec `command_delay` dans `config/motors.yaml`) ;
  - mode terminal `TERM` : en `TERM=2`, le PS90 répond « OK » à chaque commande sans réponse ; le code ignore ces « OK », mais `TERM=0` reste le plus sûr.
- [ ] **Lectures répétées.** `wm()` sur tous les moteurs, 20 fois de suite.
  *Attendu :* toujours une réponse correcte, jamais d'erreur.
- [ ] **Mouvements normaux.** Quelques `mv` / `mvr` habituels, sur plusieurs moteurs.
  *Attendu :* comportement identique à avant (vérifie que la lecture jusqu'au terminateur ne casse pas le suivi de mouvement).
- [ ] **Câble série débranché.** Débrancher le câble série du PS90, puis `wm()`.
  *Attendu :* erreur claire (timeout, ou port série perdu) en environ 1 s, sans blocage du shell ni du serveur.
- [ ] **Rebranchement.** Rebrancher le câble, puis `wm()`.
  *Attendu :* tout refonctionne. Au besoin, `/ps90/close` puis reconnexion (rechargement de la config).

Remarques / résultats :

---

## Tâche 3 : remonter les erreurs de mouvement

Préparation : choisir un axe sur lequel aller en **fin de course est sans danger**, et noter sa plage utile.

- [ ] **Mouvement normal.** `mv(moteur, position)` habituel.
  *Attendu :* aucun changement visible ; le résultat contient la position finale réelle (`'position': ...`).
- [ ] **Fin de course.** Sur l'axe choisi, `mv()` vers une position au-delà de la fin de course.
  *Attendu :* `mv()` lève une `MotionError` qui indique le moteur, la consigne, la position atteinte et l'état de l'axe avec sa signification (ex. `axis status 'L' (disabled after approaching a hardware limit switch (MINSTOP/MAXSTOP))`). Après un arrêt sur fin de course (`L`), le manuel indique de faire `INIT` puis `EFREE<n>` pour dégager l'axe.
- [ ] **Scan qui traverse la limite.** `ascan()` sur ce même axe, avec des points au-delà de la fin de course.
  *Attendu :* le scan s'arrête au premier point en erreur, affiche « Scan stopped at point i/N », et **ne ramène pas** le moteur à sa position initiale (message « NOT returned »).
- [ ] **Délai maximal.** Dans `config/motors.yaml`, mettre temporairement `max_move_duration: 2` sur un moteur, redémarrer le serveur moteurs, puis lancer un mouvement qui dure plus de 2 s, **à faible vitesse**.
  *Attendu :* l'axe est arrêté au bout de 2 s et `mv()` lève une `MotionError` « move not finished after 2.0 s, stop sent ». Ce test vérifie aussi la commande d'arrêt (`PS90_STOP_AXIS_CMD`, voir tâche 4). Remettre ensuite la valeur d'origine.
- [ ] **Tolérance de position.** Si un axe s'arrête régulièrement à ±1 pas de la consigne, régler `position_tolerance_steps` dans `config/motors.yaml` pour ce moteur.

Remarques / résultats :

---

## Tâche 4 : arrêt d'urgence

⚠️ **À faire à faible vitesse, en surveillant le banc, la main près de l'arrêt matériel.**

- [ ] **Commande d'arrêt.** Le manuel du PS90+ confirme `STOP<n>` (décélération avec la rampe réglée, puis arrêt). À confirmer sur l'ancien PS90 par le premier test ci-dessous, avant les autres. `stop_all()` arrête un à un les axes des moteurs déclarés dans `config/motors.yaml` (**pas les axes non déclarés**) : la commande générale `MSTOP` n'est pas utilisée, car le format de son masque d'axes dépend du mode `TERM`.
- [ ] **`stop(moteur)` depuis un autre shell.** Lancer un long mouvement depuis le PC A, puis `stop(moteur)` depuis le PC B.
  *Attendu :* le moteur s'arrête immédiatement. Le `mv` du PC A lève une `MotionError` « stopped by user » avec la position atteinte.
- [ ] **`stop_all()`.** Lancer des mouvements longs sur deux moteurs (deux shells), puis `stop_all()` depuis un troisième shell.
  *Attendu :* tous les moteurs s'arrêtent.
- [ ] **Reprise après arrêt.** Après un `stop`, refaire un `mv` du même moteur.
  *Attendu :* le mouvement s'effectue normalement.
- [ ] **Ctrl+C dans `tweak`.** En mode `tweak`, appuyer sur Ctrl+C.
  *Attendu :* les moteurs reçoivent un `stop`, message « Interrupted: motors stopped », retour au shell.
- [ ] **Ctrl+C pendant `mv` / `ascan`.** Lancer un long `mv`, puis Ctrl+C dans le même shell.
  *Attendu :* message « Interrupted: stopping ... » et arrêt du moteur. **Limite connue :** tant que la tâche 14 n'est pas faite, la requête de mouvement est bloquante ; sous Windows, le Ctrl+C peut n'être pris en compte qu'à la fin du mouvement (ou du timeout client). Dans ce cas, utiliser `stop()` / `stop_all()` depuis un second shell. Ce test est à refaire après la tâche 14.

Remarques / résultats :

---

## Tâche 5 : mouvement relatif sur position relue

- [ ] **Déplacement à la main.** `free(m)`, déplacer l'axe à la main, puis `control(m)` et `mvr(m, petite_valeur)`.
  *Attendu :* le déplacement part bien de la nouvelle position (vérifier avec `wm(m)` avant et après : écart = `petite_valeur`).
  D'après le manuel, `INIT` (envoyé par `control()`) ne déplace pas l'axe ; faire quand même `wm(m)` **après** `control(m)` pour avoir la position de départ.
- [ ] **Après un arrêt.** Lancer un long `mv`, l'arrêter avec `stop(m)` depuis un autre shell, puis `mvr(m, petite_valeur)`.
  *Attendu :* le déplacement part de la position où le moteur s'est arrêté.

Remarques / résultats :

---

## Tâche 6 : cohérence des adresses des serveurs

Préparation (une seule fois) :
- [ ] **Noms des PC.** Remplacer `pc-moteurs` / `pc-spectro` dans `config/servers.yaml` (et dans le tableau « Bench architecture » du `README.md`) par les vrais noms des PC du banc, tels que déclarés dans le fichier `hosts`.
  Les serveurs moteurs et FESTO tournent tous deux sur `pc-moteurs`, le spectromètre sur `pc-spectro`. **Attention :** l'ancien `start_motion.ps1` lançait le serveur moteurs en `192.168.1.3` ; il faut maintenant le lancer sur `pc-moteurs`.
- [ ] **Fichier `hosts`.** Sur **chacun des 5 PC**, vérifier que `C:\Windows\System32\drivers\etc\hosts` contient les noms utilisés (`ping pc-moteurs` doit répondre depuis chaque PC).

Tests :
- [ ] **Plus d'IP en dur.** `grep -rn "192.168" .` (ou `Select-String -Path * -Pattern "192.168" -Recurse` sous PowerShell) : seules restent les lignes d'exemple commentées de `config/servers.yaml` (et `IRLab_modifications.md`).
- [ ] **Démarrage des serveurs.** Lancer `.\start_motion.ps1` et `.\start_festo.ps1` sur `pc-moteurs` (pas `start_spectro.ps1`, spectro désactivé).
  *Attendu :* chaque script affiche le bon port (8001 / 8003) et uvicorn écoute sur `0.0.0.0`.
- [ ] **Shell depuis n'importe quel PC.** Lancer `python IRLab_shell.py` depuis au moins deux PC différents du banc (dont un qui ne fait tourner aucun serveur).
  *Attendu :* les trois serveurs sont joignables (« ... server running »).
- [ ] **Pare-feu** (si un serveur n'est pas joignable depuis un autre PC alors qu'il l'est en local) : les ports 8001 à 8003 doivent être ouverts en entrée sur les PC serveurs (traité en détail à la tâche 17).

Remarques / résultats :

---

## Tâche 7 : timeouts côté client adaptés

- [ ] **Longue exposition.** *(reporté : spectro désactivé)* `spec.acquire(exposure=8)`.
  *Attendu :* le spectre est renvoyé, sans timeout (avant : échec systématique au-delà de 5 s).
- [ ] **Long déplacement.** Un déplacement de plus d'une minute (grande course et/ou vitesse réduite).
  *Attendu :* `mv()` aboutit sans timeout côté client (avant : abandon à 60 s pendant que le moteur bougeait encore).
  Le timeout client vaut maintenant `max_move_duration` du moteur (120 s par défaut, réglable dans `config/motors.yaml`) + 30 s. Pour un déplacement de plus de 2 min, augmenter `max_move_duration` pour ce moteur.

Remarques / résultats :

---

## Tâche 8 : chargement de la config au démarrage

**Nouveau fonctionnement :** les serveurs moteurs et FESTO chargent leur config tout seuls au démarrage. Les axes ne sont **plus initialisés automatiquement** : après chaque démarrage du serveur moteurs, taper `init_all()` dans le shell : il met les moteurs sous puissance (d'après le manuel, `INIT` ne déplace pas les axes ; à confirmer sur l'ancien PS90). Tant que ce n'est pas fait, les mouvements sont refusés (« not initialized »).

- [ ] **Moteurs listés sans le shell.** Démarrer le serveur moteurs, puis ouvrir dans un navigateur `http://pc-moteurs:8001/motors/list`.
  *Attendu :* les 6 moteurs sont listés (état `off`), **sans** avoir lancé le shell, et sans qu'aucun axe n'ait bougé.
- [ ] **`/status`.** Ouvrir `http://pc-moteurs:8001/status`, `http://pc-moteurs:8003/status` (spectro : reporté).
  *Attendu :* JSON avec le nom du serveur, la version (`"version": "1.0"`), `"status": "ok"` et les contrôleurs `connected`.
- [ ] **Version affichée.** Lancer les serveurs moteurs et FESTO, puis le shell.
  *Attendu :* la console de chaque serveur affiche `<serveur> v1.0` au démarrage (aussi écrit dans `logs/`), le shell affiche `IRLab shell v1.0` sous la bannière, et chaque serveur joignable est listé avec `(v1.0)`, sans avertissement de version différente.
- [ ] **Shell et `init_all()`.** Lancer le shell.
  *Attendu :* message « Not initialized yet: ... Run init_all() ». Un `mv` est refusé (« not initialized »). Après `init_all()` (en surveillant le banc), les `mv` fonctionnent.
- [ ] **Pas d'INIT à l'ouverture d'un shell.** Une fois les moteurs initialisés, ouvrir un second shell sur un autre PC.
  *Attendu :* aucun axe ne bouge, et pas de message « Not initialized ».
- [ ] **PS90 débranché au démarrage.** Arrêter le serveur moteurs, débrancher le câble série du PS90, redémarrer le serveur.
  *Attendu :* le serveur démarre quand même ; `/status` indique `"status": "degraded"` et l'erreur du port COM ; le shell affiche cette erreur.
- [ ] **Reprise avec `/admin/reload_config`.** Rebrancher le câble, puis aller sur `http://pc-moteurs:8001/docs`, endpoint `POST /admin/reload_config`, « Try it out » → « Execute ».
  *Attendu :* les moteurs apparaissent (`created`), `/status` repasse à `ok`. Puis `init_all()` dans le shell.
- [ ] **Arrêt du serveur pendant un mouvement.** Lancer un long `mv` (faible vitesse), puis Ctrl+C dans la fenêtre du serveur moteurs.
  *Attendu :* l'axe est arrêté avant la fermeture du port série (message « Shutdown: stopped moving motor ... »).
- [ ] **FESTO.** Même chose côté FESTO : `http://pc-moteurs:8003/festo/actuators/list` liste les actionneurs sans passer par le shell ; `on(...)` / `off(...)` fonctionnent depuis le shell.

Remarques / résultats :

---

## Tâche 9 : simplifier l'enregistrement des moteurs et le shell

Le shell ne lit plus `config/motors.yaml` / `config/festo.yaml` : il crée ses objets uniquement à partir de `/motors/list` et `/festo/actuators/list`. Les endpoints `/ps90/register`, `/ps90/list`, `/ps90/load_config`, `/motors/register`, `/festo/load_config` et `/festo/actuators/register` n'existent plus.

- [ ] **Mêmes objets qu'avant.** Lancer le shell.
  *Attendu :* les mêmes moteurs (`faty`, `focdy`, `focuy`, `sx`, `sy`, `sz`) et actionneurs (`festo_1` à `festo_10`) sont créés ; chaque ligne moteur affiche aussi son unité. `mv`, `wm`, `on`, `off` fonctionnent comme avant.
- [ ] **`/motors/list`.** Dans un navigateur, `http://pc-moteurs:8001/motors/list`.
  *Attendu :* chaque moteur a `unit` et `state` en plus des champs habituels.
- [ ] **Reconnexion du PS90 sans redémarrer le serveur** (remplace « `/ps90/close` puis reconnexion » de la tâche 2). Sur `http://pc-moteurs:8001/docs` : `POST /ps90/close` (name = `main_ps90`), puis `POST /admin/reload_config`, puis `init_all()` dans le shell.
  *Attendu :* les moteurs disparaissent après le `close`, réapparaissent après le `reload_config`, et fonctionnent après `init_all()`. Relancer le shell (ou `reconnect()`, tâche 10) pour retrouver les objets à jour.

Remarques / résultats :

---

## Tâche 10 : shell tolérant à un serveur absent

- [ ] **Seul le serveur FESTO démarré.** Arrêter le serveur moteurs, lancer le shell.
  *Attendu :* avertissement « Motion server NOT reachable » (spectro affiché `DISABLED`, sans avertissement), mais le shell démarre ; le récapitulatif indique `FESTO server OK`, `0 motor(s), 10 actuator(s)`. `on(festo_1)` / `off(festo_1)` fonctionnent.
- [ ] **`reconnect()`.** Démarrer ensuite le serveur moteurs, puis `reconnect()` dans le même shell.
  *Attendu :* les moteurs apparaissent (`sx`, `sy`...), le récapitulatif indique `Motion server OK` et `6 motor(s)`. Après `init_all()`, `mv` fonctionne.
- [ ] **Aucun serveur.** Lancer le shell sans aucun serveur démarré.
  *Attendu :* le shell démarre quand même (0 moteur, 0 actionneur) en environ 2 s par serveur absent, sans exception.

Remarques / résultats :

---

## Tâche 11 : actions en POST plutôt qu'en GET

⚠️ **Mettre à jour le code sur tous les PC en même temps** (serveurs et shells) : un ancien shell ne peut plus piloter un nouveau serveur (et inversement).

- [ ] **Shell inchangé.** `init_all()`, `mv`, `mvr`, `wm`, `free`, `control`, `stop`, `ascan`, `tweak`, `on`, `off`, `toggle`, `state` (`spec.acquire(...)` : reporté).
  *Attendu :* tout fonctionne comme avant.
- [ ] **Navigateur sans effet.** Ouvrir `http://pc-moteurs:8001/motors/move_abs/sx` dans un navigateur.
  *Attendu :* erreur 405 « Method Not Allowed », aucun mouvement. (L'ancienne forme `.../motors/move_abs/sx/100` renvoie 404, sans mouvement non plus.) Idem pour `http://pc-moteurs:8003/festo/actuators/on/festo_1` : 405, l'actionneur ne bouge pas.
- [ ] **`/docs`.** Sur `http://pc-moteurs:8001/docs`, `POST /motors/move_rel/{motor}` → « Try it out », motor = `sx`, corps `{"delta": 100}` → « Execute ».
  *Attendu :* le moteur se déplace de 100 pas ; la réponse contient la position finale.
- [ ] **Scripts personnels.** Si des scripts appellent directement les URL des serveurs (`requests.get(.../move_abs/...)`), les adapter (voir la liste des endpoints dans `docs/TECHNICAL.md`).

Remarques / résultats :

---

## Tâche 12 : journalisation persistante

- [ ] **Trace d'un mouvement distant.** Depuis un autre PC que `pc-moteurs`, faire un `mv(sx, ...)`. Sur `pc-moteurs`, ouvrir `logs\motion_server.log` (dans le dossier du dépôt).
  *Attendu :* deux lignes `POST /motors/move_abs/sx {"position": ...} from <IP du PC>` : `started`, puis `HTTP 200 in ... s -> {... 'position': ...}`.
- [ ] **Trace d'une erreur.** Provoquer une erreur (ex. `mv` d'un moteur avant `init_all()`).
  *Attendu :* ligne `ERROR` avec le message d'erreur.
- [ ] **FESTO.** Un `on(festo_1)` apparaît dans `logs\festo_server.log`.
- [ ] **Spectro.** *(reporté : spectro désactivé)* Un `spec.acquire(...)` apparaît dans `logs\spectro_server.log` sur `pc-spectro`.
- [ ] **Log série (diagnostic).** Mettre `log_serial: true` dans `config/motors.yaml`, redémarrer le serveur moteurs, faire un `wm(sx)`.
  *Attendu :* lignes `COM25 >> ?CNT2` et `COM25 << b'...'` dans le log, **ce qui montre aussi le caractère de fin de réponse réel du PS90** (à comparer avec `PS90_TERMINATOR`, tâche 2). Remettre `log_serial: false` ensuite.
- [ ] **Rotation.** Le lendemain, vérifier qu'un fichier `motion_server.log.AAAA-MM-JJ` a été créé.

Remarques / résultats :

---

## Tâche 15 : petits bugs et nettoyage

- [ ] **Unités.** `config/motors.yaml` indique maintenant `unit:` pour chaque moteur (`mm` pour `sx`, `sy`, `sz`, `steps` pour `faty`, `focdy`, `focuy`). **Vérifier que ces unités sont les bonnes** (en particulier pour `faty`, `focdy`, `focuy` : s'ils devraient être en mm ou en degrés, renseigner `unit` et `step_to_mm`).
- [ ] **`mv(m, 2)` = `mv(m, 2.0)`.** Sur un moteur en mm, `mv(sx, 1)` puis `wm(sx)`, puis `mv(sx, 1.0)` : même position. `sx.position()` renvoie la position en mm.
- [ ] **Scans et `tweak`.** Un petit `dscan(sx, -0.1, 0.1, 3)` revient bien à la position de départ ; `tweak(sx)` affiche les positions dans l'unité du moteur.
- [ ] **Paramètres d'un axe.** Ouvrir `http://pc-moteurs:8001/motors/parameters/sx`.
  *Attendu :* JSON avec le mode, la vitesse, l'accélération, les compteurs. **Noter** la réponse à `?MODE` (absolu / relatif) pour la doc.
- [ ] **Vitesse / accélération.** Après démarrage du serveur moteurs, `/status` ne contient pas d'erreur `Failed to set PVEL...` ; les valeurs de `/motors/parameters/<moteur>` correspondent à `velocity` / `acceleration` de `config/motors.yaml`.
- [ ] **Deuxième serveur moteurs.** Avec un serveur moteurs déjà lancé, en démarrer un second sur le même PC (autre port : `.\start_motion.ps1 -Port 8011`).
  *Attendu :* le second démarre en mode dégradé, et son `/status` indique « Serial port COM25 is already in use by another program (is another motion server already running?) ». L'arrêter ensuite.
- [ ] **Échec d'initialisation visible.** (Si l'occasion se présente : axe débranché, alimentation coupée...) `init(m)` affiche l'erreur au lieu de la passer sous silence ; le moteur passe en `fault`.
- [ ] **FESTO `close`.** Sur `http://pc-moteurs:8003/docs` : `POST /festo/close` (name = `main_festo`), puis `GET /festo/actuators/list` → vide ; puis `POST /admin/reload_config` → les actionneurs reviennent.

Remarques / résultats :

---

## Corrections après la revue globale

- [ ] **Acquisition.** *(reporté : spectro désactivé)* `spec.acquire(exposure=0.1)` renvoie bien un spectre (avant : erreur 500 probable si le SDK Andor renvoie des tableaux numpy).
- [ ] **FESTO simultanés.** Depuis deux shells sur deux PC, lancer en même temps une boucle `for i in range(20): toggle(festo_1)` (sur un actionneur sans danger).
  *Attendu :* aucune erreur NI-DAQmx « resource reserved ».
- [ ] **Commandes non bloquées.** Après mise à jour, les `mv`, `on`, `init_all()` répondent normalement et apparaissent dans les logs avec leurs paramètres (vérifie le nouveau mécanisme de journalisation sur la version de Starlette installée sur le banc).

Remarques / résultats :

---

## Points issus du manuel PS90+

- [ ] **Profil de mouvement.** Les mouvements fonctionnent quel que soit le profil réglé dans le PS90 (trapézoïdal `T` ou S-curve `S`) : la fin de mouvement attend maintenant tous les états de mouvement du manuel (`T, S, V, P, F, W, X, Y, C, N`), et plus seulement `T`. Un `mv` normal doit se terminer sans « wrong final position ».
- [ ] **`INIT` ne bouge pas.** Pendant `init_all()`, vérifier qu'aucun axe ne se déplace.

Remarques / résultats :

---

## Tâche 17 : scripts de démarrage et documentation

(Les scripts `.ps1` n'ont pas pu être exécutés hors Windows : ces tests sont les premiers à les faire tourner.)

- [ ] **Lancement depuis un autre dossier.** Depuis `C:\` : `& "C:\<chemin>\IRLab\start_motion.ps1"`.
  *Attendu :* le serveur démarre sur le port de `config/servers.yaml` (8001).
- [ ] **`.venv` absent.** Renommer temporairement `.venv` en `.venv_old`, lancer `start_motion.ps1`.
  *Attendu :* message rouge « Python virtual environment not found ... », pas de traceback. Remettre `.venv`.
- [ ] **Port explicite.** `.\start_motion.ps1 -Port 8011` démarre sur 8011 (l'arrêter ensuite).
- [ ] **Politique d'exécution.** Si Windows refuse le script : `powershell -ExecutionPolicy Bypass -File .\start_motion.ps1` fonctionne.
- [ ] **Pare-feu.** Appliquer la règle de `docs/TECHNICAL.md` (section Firewall) sur `pc-moteurs` (et `pc-spectro` plus tard), puis lancer le shell depuis un autre PC : les serveurs moteurs et FESTO sont joignables.
- [ ] **(Optionnel) Démarrage automatique.** Si souhaité, créer la tâche planifiée de `docs/TECHNICAL.md` pour un serveur, fermer la session puis la rouvrir : le serveur démarre tout seul.
- [ ] **Documentation.** Relire le `README.md` (noms des PC dans « Bench architecture ») et, dans `docs/TECHNICAL.md`, « Points to check on the hardware » et « Upgrading from the previous version ».

Remarques / résultats :

