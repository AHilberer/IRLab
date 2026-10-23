# IRLab : liste des modifications à réaliser

> **À l'attention de Claude Code.** Ce fichier décrit les modifications à apporter au
> dépôt IRLab (framework Python de contrôle d'un banc de spectroscopie optique).
> Lis d'abord la section « Contexte et règles », puis traite les tâches dans l'ordre
> indiqué. Chaque tâche précise les fichiers concernés, ce qu'il faut faire, et un
> test à réaliser sur le banc par l'utilisateur.

---

## Contexte et règles

### Le système

- Les **serveurs FastAPI** pilotent chacun un matériel :
  - `servers/motion_server.py` : moteurs, via un contrôleur OWIS PS90 sur port série ;
  - `servers/spectro_server.py` : spectromètre, via les SDK Andor (caméra) et Shamrock (spectrographe) ; code écrit mais pas encore testé sur le banc, serveur désactivé depuis la v1.1 (`disabled_servers` dans `config/servers.yaml`) ;
  - `servers/festo_server.py` : vérins pneumatiques FESTO, via NI-DAQmx.
- Les **clients HTTP** (`clients/`) et le shell **IPython** (`IRLab_shell.py`) offrent des commandes inspirées de SPEC : `mv`, `mvr`, `wm`, `ascan`, `dscan`, `tweak`, `on`, `off`…
- Le tout tourne sur **5 PC Windows 10/11** reliés par un switch, sur un réseau local **isolé d'Internet**. Les noms des machines sont résolus par le fichier `hosts`.
- **Le système fonctionne déjà sur le banc.** Le but est de le fiabiliser, pas de le réécrire.

### Règles de travail

1. **Modifications ciblées.** Pas de refonte d'architecture, pas de couche d'abstraction ni de mode simulation dans le code des serveurs. Chaque changement doit rester lisible et facile à relire par l'utilisateur.
2. **Tu n'as pas accès au matériel.** Tu ne peux donc pas tester les changements sur le banc.
   - Vérifie au minimum que le code s'importe et que les serveurs démarrent (`python -c "import servers.motion_server"`, etc.).
   - Pour la logique série (tâches 1 à 5), un faux objet série **dans `tests/` uniquement** est autorisé (voir l'annexe « Tests »), sans aucune modification du code de production pour l'accueillir.
   - Chaque tâche se termine par un test sur le banc, à réaliser par l'utilisateur. Reprends ces tests dans ton résumé final.
3. **Protocole PS90.** Ne pas inventer de commandes ni de format de réponse. Quand une tâche dépend d'un détail du protocole (caractère de fin de réponse, commande d'arrêt, codes d'état), centraliser ce détail dans une constante clairement nommée, avec un commentaire `# À VÉRIFIER dans le manuel OWIS PS90`. Le signaler ensuite dans le résumé final.
4. **Garder l'interface du shell.** Les signatures de `mv`, `mvr`, `wm`, `free`, `control`, `ascan`, `dscan`, `tweak`, `on`, `off`, `toggle` et `state` doivent rester compatibles. Les nouveaux paramètres sont optionnels, avec des valeurs par défaut sûres.
5. **Une tâche = un commit**, avec un message clair. L'utilisateur pourra ainsi tester sur le banc et revenir en arrière tâche par tâche.
6. **Le code doit tourner sur Windows** : chemins avec `pathlib`, pas de dépendance propre à Linux. Le code non-Windows existant de `tweak` est conservé.
7. **Langue.** Le code et les noms en anglais (comme l'existant). Les messages affichés à l'utilisateur peuvent rester en anglais.
8. **À la fin**, mettre à jour `README.md` et produire un résumé des changements, avec la liste des points `À VÉRIFIER`.

### État d'avancement

Version actuelle : **v1.2**, sur `main` (pull requests #1 `reliability-improvements` → `develop`, puis #2 `develop` → `main`).

| Version | Contenu | Banc |
|---|---|---|
| v1.0 | tâches ci-dessous + numéro de version affiché (shell, consoles et logs des serveurs, `/status`) | — |
| v1.1 | serveur spectro désactivé (`disabled_servers`) en attendant ses tests | testée : moteurs et FESTO validés (`TESTS_BANC.md`) |
| v1.2 | corrections issues des tests de la v1.1 : châssis FESTO `cDAQ3`, état FESTO juste après redémarrage, réouverture du port série après rebranchement, erreurs affichées par `wm()`, `reconnect()` relance la config d'un serveur dégradé (`/docs` inutilisable hors ligne) | à tester (voir ci-dessous) |
| v1.3 | tâche 16 : Python 3.13.17 (python.org, plus Anaconda) sur tous les PC, versions figées dans `requirements.txt` (`pip freeze` de pc-moteurs), `tools/download_wheels.ps1` et `tools/install_offline.ps1` ; paquets Andor reportés aux tests du spectro | à tester (`TESTS_BANC.md`, tâche 16) |
| v1.4 | `start_shell.ps1` : lance le shell depuis n'importe quel dossier | à tester avec la v1.3 (tâche 16) |

Les changements sont désormais regroupés en versions (`VERSION` dans `common/version.py` + tag git `vX.Y`), plutôt que copiés commit par commit sur le banc.

| # | Tâche | Priorité | État |
|---|---|---|---|
| 1 | Verrou d'accès au port série | critique | fait (`e689b71`) |
| 2 | Lecture série robuste | critique | fait (`61dbe23`) |
| 3 | Remonter les erreurs de mouvement | critique | fait (`dfbd607`) |
| 4 | Arrêt d'urgence | critique | fait (`7afa3a1`) |
| 5 | Mouvement relatif sur position relue | critique | fait (`05ebdbe`) |
| 6 | Cohérence des adresses des serveurs | critique | fait (`322267a`) |
| 7 | Timeouts côté client adaptés | important | fait (`71061a5`) |
| 8 | Chargement de la config au démarrage (lifespan) | important | fait (`6b8196b`) |
| 9 | Simplifier l'enregistrement des moteurs et le shell | important | fait (`fede70b`) |
| 10 | Shell tolérant à un serveur absent | important | fait (`7fc70d1`) |
| 11 | Actions en POST plutôt qu'en GET | important | fait (`77d979c`) |
| 12 | Journalisation persistante | important | fait (`1423f08`) |
| 13 | Scans qui acquièrent et enregistrent les données | fonctionnel | **à faire** |
| 14 | Mouvements simultanés dans `mv` | fonctionnel | **à faire** |
| 15 | Petits bugs et nettoyage | qualité | fait (`f400df0`) |
| 16 | Versions figées et installation hors ligne | déploiement | fait (v1.3) |
| 17 | Scripts de démarrage et documentation | déploiement | fait (`b2b35bf`, `3d0aa74`), à compléter après 13 et 16 |

Travaux faits en plus : revue globale du code (`814f19e`) et alignement du protocole PS90 sur le manuel du PS 90+ (`576de61`).

### Tâches restantes, par ordre de priorité

1. **Tâche 13 : scans qui acquièrent et enregistrent les données (HDF5).**
2. **Tâche 14 : mouvements simultanés dans `mv`.** Rend aussi possible le Ctrl+C pendant un `mv` (constaté sur le banc : pris en compte seulement à la fin du mouvement), et éventuellement l'arrêt des axes par Ctrl+C dans la fenêtre du serveur moteurs (aujourd'hui, le serveur attend la fin du mouvement en cours).
3. **Spectromètre** : tester le serveur spectro sur `pc-spectro` (chemin d'import de `ATSpectrograph`, appels au SDK), installer les paquets Andor hors ligne depuis les SDK (reporté de la tâche 16), puis le réactiver (`disabled_servers: []`). Tests marqués « reporté » dans `TESTS_BANC.md`.
4. **Tâche 17 : compléter la documentation** : format HDF5, circuit local → partage, `sync_data`, `IRLAB_DATA_DIR` et `IRLAB_LOCAL_DATA_DIR` (après 13).

### À vérifier sur le banc

- **v1.2** : après débranchement puis rebranchement du câble série, `wm()` affiche une erreur claire, puis refonctionne sans redémarrer le serveur moteurs ; juste après un redémarrage du serveur FESTO, `check_all()` affiche `festo_server: on` ; PS90 débranché au démarrage, rebranché, puis `reconnect()` : les moteurs apparaissent.
- **`start_motion.ps1` lancé depuis un autre dossier** (`& "C:\<chemin>\IRLab\start_motion.ps1"`) ne marche pas : relever le message d'erreur exact pour corriger le script.
- **Tests reportés par l'utilisateur** : fins de course et délai maximal (tâche 3 : savoir d'abord quels axes ont des fins de course), rotation des logs (tâche 12), autres profils de mouvement du PS90.

---

## 1. Verrou d'accès au port série (critique)

**Pourquoi.** FastAPI exécute les routes `def` en parallèle dans un pool de threads. Plusieurs requêtes simultanées entremêlent alors leurs commandes et leurs réponses sur le port série du PS90. Cela arrive dès qu'un `wm()` part d'un autre PC pendant un `mv()`, ou avec le rafraîchissement de `tweak`. On obtient des positions fausses, ou un `int()` qui plante sur une réponse tronquée.

**Fichiers.** `servers/motion_server.py` (classes `PS90`, `PS90_motor`).

**À faire.**

- Ajouter un `threading.RLock` par contrôleur. `send()` prend le verrou pour toute la séquence vider le tampon, écrire, lire.
- **Séquences multi-commandes.**
  - Ces séquences doivent être atomiques vis-à-vis des autres clients : `PSET` puis `PGO`, init (`AXIS=1` puis `INIT`), lecture des paramètres.
  - Prendre le même verrou réentrant autour de chacune.
  - **Ne pas** garder le verrou pendant toute l'attente de fin de mouvement : la boucle de polling prend et relâche le verrou à chaque `?ASTAT`. Sinon, `wm` et l'arrêt d'urgence seraient bloqués pendant un mouvement.
- **Un seul mouvement à la fois par moteur.** Ajouter un verrou de mouvement par moteur. Une deuxième demande de mouvement sur un moteur déjà en mouvement renvoie immédiatement une erreur HTTP 409 (« motor busy »), au lieu d'attendre.

**Test sur le banc.** Lancer un long `mv` depuis un PC et, pendant le mouvement, faire plusieurs `wm()` depuis un autre PC. Les positions lues sont cohérentes et aucune erreur n'apparaît. Un second `mv` du même moteur pendant le mouvement renvoie « motor busy ».

---

## 2. Lecture série robuste (critique)

**Pourquoi.** `PS90.send()` fait `sleep(0.05)` puis `read_all()`. Si le PS90 répond en plus de 50 ms, la réponse est vide ou coupée. Les commandes sans réponse attendent aussi 50 ms pour rien.

**Fichiers.** `servers/motion_server.py`.

**À faire.**

- **Distinguer les deux types de commandes** :
  - les requêtes, qui commencent par `?`, attendent une réponse ;
  - les commandes sans `?` n'en attendent pas.
- **Pour les requêtes**, lire avec `ser.read_until(TERMINATOR)` en s'appuyant sur le timeout du port (1 s, configurable). Si le terminateur n'arrive pas, lever une `TimeoutError` avec la commande en clair dans le message.
  - `TERMINATOR` est une constante `# À VÉRIFIER dans le manuel OWIS PS90`. Par défaut, `b'\r'`, à confirmer.
- **Pour les commandes sans réponse**, écrire, puis un éventuel court délai configurable (à confirmer dans le manuel).
- **Valider les réponses numériques.** Dans `read_current_position()`, si la réponse à `?CNT` n'est pas un entier, lever une erreur explicite (`ValueError` avec la réponse reçue) au lieu d'un plantage `int()` cryptique.
- **Valider `?ASTAT`.** `get_status()` renvoie aujourd'hui une phrase d'erreur (« Problem getting status… ») à la place de la chaîne d'état, phrase que `initialize_axis()` indexe ensuite comme une chaîne d'état. À la place, lever une exception si la réponse est vide ou trop courte pour l'axe demandé.

**Test sur le banc.** `wm()` sur tous les moteurs, 20 fois de suite : toujours une réponse correcte. Débrancher le câble série du PS90 : `wm()` renvoie une erreur claire en environ 1 s, sans blocage. Rebrancher : tout refonctionne (au besoin après `/ps90/close` et reconnexion).

---

## 3. Remonter les erreurs de mouvement (critique)

**Pourquoi.** Aujourd'hui, un mouvement raté passe inaperçu :

- `move_absolute()` boucle sans limite de durée tant que l'axe est en mouvement ;
- si la position finale est fausse (fin de course, blocage), le serveur écrit « Wrong final position » dans sa console et renvoie `{"result": null}` avec un HTTP 200 ;
- côté client, `mv()` et `mvr()` attrapent toutes les exceptions et les rangent dans une liste ;
- `ascan` et `dscan` ne regardent jamais cette liste.

Un scan continue donc avec un moteur bloqué.

**Fichiers.** `servers/motion_server.py`, `clients/motion_client.py`, `scripts/base_scripts.py`, nouveau `common/errors.py`.

**À faire.**

- **Côté serveur.**
  - `move_absolute()` a un délai maximal, configurable par moteur dans le YAML (`max_move_duration`, en secondes, avec un défaut raisonnable comme 120 s). S'il est dépassé : envoyer l'arrêt (tâche 4) et lever une erreur.
  - Une position finale différente de la consigne, au-delà d'une tolérance configurable par moteur (`position_tolerance_steps`, défaut 0), lève une erreur.
  - Lire l'état de l'axe à la fin du mouvement et l'inclure dans le message d'erreur (fin de course, etc.).
- **Côté HTTP.** Les erreurs de mouvement renvoient un code HTTP non-200 (500, ou 409 pour « busy ») avec un `detail` lisible : moteur, consigne, position atteinte, état de l'axe. En cas de succès, la réponse contient la position finale réelle.
- **Côté client.**
  - Créer une exception `MotionError` (dans `common/errors.py`).
  - Dans `safe_get` (ou son remplaçant, voir tâche 11), vérifier le code HTTP. Si ce n'est pas un succès, lever une exception qui contient le `detail` renvoyé par le serveur.
  - `mv()` et `mvr()` **lèvent** l'exception au lieu de la mettre dans une liste. Un paramètre optionnel `raise_on_error=True` permet de garder l'ancien comportement si on le met à `False`.
- **Côté scans.** `ascan` et `dscan` s'arrêtent à la première erreur, affichent clairement le point atteint, et ne tentent **pas** de revenir automatiquement à la position initiale si le moteur est en erreur. Ils l'indiquent à l'utilisateur.

**Test sur le banc.** Demander un mouvement vers une position au-delà d'une fin de course, sur un axe où c'est sans danger : `mv()` lève une `MotionError` qui mentionne la position atteinte et l'état de l'axe. Lancer un `ascan` qui traverse cette limite : le scan s'arrête au bon point avec un message clair.

---

## 4. Arrêt d'urgence (critique)

**Pourquoi.** Un Ctrl+C dans le shell coupe la requête HTTP, mais le moteur continue sa course. Il n'existe aucun moyen d'arrêter un mouvement.

**Fichiers.** `servers/motion_server.py`, `clients/motion_client.py`, `scripts/base_scripts.py`, `IRLab_shell.py`.

**À faire.**

- **Côté serveur.**
  - Ajouter `PS90_motor.stop()`. La commande d'arrêt d'un axe est une constante `# À VÉRIFIER dans le manuel OWIS PS90` : chercher la commande d'arrêt d'axe et celle d'arrêt général du contrôleur.
  - L'arrêt **ne doit pas attendre** le verrou de mouvement de la tâche 1. Il prend seulement le verrou série, pendant une seule commande.
  - Endpoints : `POST /motors/stop/{motor}` et `POST /motors/stop_all`, qui arrête tous les axes de tous les contrôleurs.
  - Une boucle d'attente de mouvement interrompue par un arrêt se termine proprement par une erreur « stopped by user ».
- **Côté client.** Fonctions `stop(*motors)` et `stop_all()`, exposées dans le shell.
- **Gestion du Ctrl+C.**
  - Dans `mv`, `mvr`, `ascan`, `dscan` et `tweak`, attraper `KeyboardInterrupt`, envoyer `stop` aux moteurs concernés, puis relancer l'interruption.
  - Pour que ce soit possible pendant un mouvement, la requête de mouvement ne doit pas bloquer de façon non interruptible. Voir la tâche 14 : séparer « lancer le mouvement » et « attendre la fin » permet d'attendre côté client par polling interruptible. Si la tâche 14 n'est pas encore faite, un `stop_all()` lancé depuis un second shell doit au minimum fonctionner.

**Test sur le banc.** À faire à **faible vitesse**, en surveillant le banc et la main près de l'arrêt matériel. Lancer un long mouvement, puis :

- `stop(moteur)` depuis un autre shell : le moteur s'arrête immédiatement ;
- `stop_all()` : tous les moteurs s'arrêtent ;
- Ctrl+C pendant `mv` (après la tâche 14) : le moteur s'arrête.

---

## 5. Mouvement relatif sur position relue (critique)

**Pourquoi.** `move_relative()` calcule la cible à partir de `current_position_step`, c'est-à-dire la dernière valeur lue. Cette valeur est fausse après un `free()` suivi d'un déplacement à la main, après un mouvement interrompu ou après une action d'un autre client.

**Fichiers.** `servers/motion_server.py`.

**À faire.** Dans `move_relative()`, relire la position (`?CNT`) juste avant de calculer la cible, sous le verrou de mouvement. Garder `current_position_step` uniquement comme information, jamais comme référence de calcul.

**Test sur le banc.** `free(m)`, déplacer l'axe à la main, puis `control(m)` et `mvr(m, petite_valeur)` : le déplacement part bien de la nouvelle position.

---

## 6. Cohérence des adresses des serveurs (critique)

**Pourquoi.** `config/servers.yaml` indique le serveur moteurs en `192.168.1.2`, mais `start_motion.ps1` le lance sur `192.168.1.3`. Le shell ne le trouve donc pas. Les IP sont aussi écrites en dur à deux endroits.

**Fichiers.** `config/servers.yaml`, `start_*.ps1`, `README.md`.

**À faire.**

- Les scripts de démarrage lancent les serveurs avec `--host 0.0.0.0`. Le port est lu depuis la config ou passé en paramètre.
- `config/servers.yaml` utilise les **noms de machines** du fichier `hosts`. Exemple :
  ```yaml
  motion_server: "http://pc-moteurs:8001"
  spectro_server: "http://pc-spectro:8002"
  festo_server: "http://pc-moteurs:8003"
  ```
  Laisser des commentaires indiquant de remplacer les noms par ceux du banc.
- Ajouter dans le README un tableau « quel serveur tourne sur quel PC, sur quel port ».

**Test sur le banc.** Plus aucune IP en dur dans le dépôt en dehors des exemples commentés (`grep -rn "192.168" .`). Le shell lancé depuis n'importe quel PC du banc joint les trois serveurs.

---

## 7. Timeouts côté client adaptés (important)

**Pourquoi.** Deux timeouts côté client sont trop courts :

- `Spectrometer.acquire()` utilise le timeout par défaut de 5 s, donc une exposition de plus de 5 s échoue toujours ;
- `mv()` a 60 s de timeout, alors qu'un long déplacement peut dépasser cette durée. Le client abandonne pendant que le moteur bouge encore.

**Fichiers.** `clients/spectro_client.py`, `clients/motion_client.py`.

**À faire.**

- `acquire(exposure, timeout=None)` : si `timeout` est `None`, utiliser `exposure + marge`, avec une marge configurable de 10 s par défaut.
- Pour les mouvements, le timeout HTTP par défaut est au moins égal au `max_move_duration` du serveur (tâche 3), plus une marge. Avec la tâche 14 (lancer puis attendre), le timeout HTTP ne porte plus que sur des requêtes courtes.

**Test sur le banc.** `spec.acquire(exposure=8)` réussit. Un long déplacement de plus d'une minute aboutit sans timeout côté client.

---

## 8. Chargement de la config au démarrage (important)

**Pourquoi.** Les serveurs démarrent vides : c'est le shell qui leur demande de charger leur config. `@app.on_event` est par ailleurs déprécié dans FastAPI.

**Fichiers.** `servers/motion_server.py`, `servers/festo_server.py`.

**À faire.**

- Utiliser le `lifespan` de FastAPI.
  - **Au démarrage** : charger le YAML (chemin par défaut, ou variable d'environnement `IRLAB_MOTORS_CONFIG` / `IRLAB_FESTO_CONFIG`), ouvrir les contrôleurs et enregistrer les moteurs et actionneurs.
  - **À l'arrêt** : fermer proprement les contrôleurs. Côté moteurs, arrêter les axes en mouvement avant de fermer.
- **Initialisation des axes.** L'option `initialize_on_startup` du YAML, à `false` par défaut, contrôle si les axes sont initialisés au démarrage. L'initialisation peut déplacer des axes, il ne faut donc pas la faire sans le vouloir.
- **Erreur de matériel au démarrage** (port COM absent, etc.) : le serveur démarre quand même, en mode dégradé.
  - `/status` renvoie un état structuré (JSON) avec les contrôleurs en erreur et le message correspondant.
  - L'endpoint `/admin/reload_config` permet de réessayer.
- **`/status`** renvoie du JSON sur les trois serveurs : nom du serveur, version, contrôleurs et leur état.

**Test sur le banc.** Démarrer le serveur moteurs, puis appeler directement `/motors/list` depuis un navigateur (`http://pc-moteurs:8001/motors/list`) : les moteurs sont listés sans passer par le shell. Démarrer le serveur avec le PS90 débranché : il démarre, et `/status` indique l'erreur. Rebrancher, puis `/admin/reload_config` : les moteurs apparaissent.

---

## 9. Simplifier l'enregistrement des moteurs et le shell (important)

**Pourquoi.** La logique est en double à plusieurs endroits :

- il existe trois façons d'enregistrer un moteur côté serveur (`/ps90/register/{name}/{axis}`, `/motors/register`, `/ps90/load_config`) ;
- il y a deux listes, `/ps90/list` et `/motors/list` ;
- le shell enchaîne plusieurs replis imbriqués (config serveur, puis config locale, puis enregistrement sur le serveur) ;
- côté client, `build_motor_list_from_config` relit aussi le YAML.

**Fichiers.** `servers/motion_server.py`, `servers/festo_server.py`, `clients/*.py`, `IRLab_shell.py`.

**À faire.**

- **Le serveur est l'unique source de vérité** sur les moteurs et les actionneurs (config chargée au démarrage, tâche 8).
- **Supprimer** `/ps90/register/{name}/{axis}` et `/ps90/list`. Garder `/motors/list`, et l'enrichir avec l'unité et l'état.
- **Rendre `/motors/register` optionnel**, réservé au débogage, ou le supprimer si rien ne l'utilise. Même chose pour `/festo/actuators/register`.
- **Le shell** ne fait plus qu'interroger `/motors/list` et `/festo/actuators/list` pour créer les objets `Motor` et `PneumaticActuator`. Supprimer les replis vers la config locale et `build_*_list_from_config` côté client.
- **Factoriser** la construction des objets dans une fonction par client (ex. `motion_client.load_motors_from_server()`), et l'appeler depuis le shell.
- **Sécuriser l'injection dans `globals()`.** Le shell injecte chaque moteur et actionneur dans `globals()`. Avant, vérifier que le nom ne remplace pas une fonction existante (`mv`, `wm`, `on`, `spec`…) et que c'est un identifiant Python valide. En cas de conflit, afficher un avertissement et ne pas écraser.

**Test sur le banc.** Le shell démarre et expose les mêmes moteurs et actionneurs qu'avant. `IRLab_shell.py` est nettement plus court.

---

## 10. Shell tolérant à un serveur absent (important)

**Pourquoi.** `IRLab_shell.py`, ligne 130, lève une exception si le serveur moteurs est injoignable, même pour un utilisateur qui ne veut piloter que les FESTO ou le spectromètre.

**Fichiers.** `IRLab_shell.py`.

**À faire.**

- Un serveur absent produit un avertissement clair, et le shell démarre avec ce qui est disponible.
- Ajouter une fonction `reconnect()` dans le shell, qui retente la connexion aux serveurs absents et crée les objets manquants.
- À la fin du démarrage, afficher un récapitulatif : serveurs joignables ou non, nombre de moteurs et d'actionneurs chargés.

**Test sur le banc.** Lancer le shell avec seulement le serveur FESTO démarré : il démarre, et `on(...)` / `off(...)` fonctionnent. Démarrer ensuite le serveur moteurs, puis `reconnect()` : les moteurs apparaissent.

---

## 11. Actions en POST plutôt qu'en GET (important)

**Pourquoi.** Toutes les actions qui modifient l'état du banc (mouvements, init, free, control, on, off, toggle, connect, close, load_config) passent aujourd'hui par des requêtes GET. Un navigateur qui précharge une URL, un rafraîchissement de page ou un outil qui explore les liens peut donc déplacer un moteur.

**Fichiers.** les trois serveurs, `common/http_client.py`, les clients, `README.md`.

**À faire.**

- Passer en `@app.post` toutes les routes qui modifient l'état. Garder en GET les lectures : `read`, `list`, `state`, `status`.
- Passer les paramètres de mouvement dans un corps JSON validé par un modèle Pydantic (ex. `{"position": 1234}`), plutôt que dans l'URL.
- Dans `common/http_client.py`, ajouter `safe_post()`, et mettre en commun la vérification du code HTTP et l'extraction du `detail` d'erreur de la tâche 3. Le plus simple est une classe `ServerClient(base_url)` avec des méthodes `get` et `post`.
- Mettre à jour tous les clients et la liste des endpoints dans le README.

**Test sur le banc.** Toutes les commandes du shell fonctionnent comme avant. Ouvrir dans un navigateur `http://pc-moteurs:8001/motors/move_abs/...` renvoie une erreur 405 et ne déplace rien. La page `/docs` permet toujours de tester les actions.

---

## 12. Journalisation persistante (important)

**Pourquoi.** Les serveurs utilisent `print()`. Rien n'est conservé, donc impossible de savoir après coup qui a déplacé quoi, quand, et avec quel résultat.

**Fichiers.** les trois serveurs, nouveau `common/logging_setup.py`.

**À faire.**

- Configurer le module `logging` : sortie console, et fichier avec rotation (`logging.handlers.RotatingFileHandler` ou `TimedRotatingFileHandler`).
  - Dossier par défaut : `logs/` à la racine du dépôt, surchargeable par la variable d'environnement `IRLAB_LOG_DIR`.
  - Un fichier par serveur.
- **Journaliser chaque commande qui modifie l'état** : horodatage, IP du client (`request.client.host`), endpoint, paramètres, résultat ou erreur, durée.
- **Journaliser les commandes série** envoyées au PS90 en niveau `DEBUG`, désactivé par défaut et activable par configuration.
- Remplacer tous les `print()` des serveurs par des appels au logger.
- Ajouter `logs/` au `.gitignore`.

**Test sur le banc.** Après un `mv` lancé depuis un autre PC, le fichier de log du serveur moteurs contient une ligne avec l'IP de ce PC, le moteur, la consigne et le résultat.

---

## 13. Scans qui acquièrent et enregistrent les données (fonctionnel)

**Pourquoi.** `ascan` et `dscan` déplacent le moteur, mais n'acquièrent rien et n'enregistrent rien. `save_hdf5` existe mais n'est jamais appelée, et son format ne contient aucune métadonnée.

**Fichiers.** `scripts/base_scripts.py`, nouveau `common/datafile.py`, éventuellement nouveau `config/data.yaml`.

**À faire.**

- **Nouvelle signature** :
  ```python
  ascan(motor, start, stop, npts, exposure=None, detector=spec, save=True, comment="")
  dscan(...)  # identique
  ```
  Si `exposure` est `None`, le comportement reste celui d'aujourd'hui (mouvement seul). Cela garde la compatibilité.
- **À chaque point** :
  1. déplacer le moteur ;
  2. relire la position réelle ;
  3. acquérir un spectre ;
  4. horodater le point.
- **Écriture HDF5 au fil de l'eau**, pas seulement à la fin, pour ne rien perdre en cas de plantage. Utiliser des datasets redimensionnables :
  - `/scan/positions_set` et `/scan/positions_read` : consigne et position lue ;
  - `/scan/timestamps` : horodatage ISO ou epoch ;
  - `/scan/wavelength` : un seul dataset si les longueurs d'onde ne changent pas ;
  - `/scan/intensity` : forme `(npts, nlambda)`.
  - En attributs : commande du scan, moteur, start, stop, npts, exposition, commentaire, utilisateur Windows, nom du PC, version du code (hash git s'il est disponible), et date de début et de fin.
  - `/metadata/motors` : position de **tous** les moteurs au début du scan.
  - `/metadata/festo` : état de tous les actionneurs.
- **Écriture locale, puis copie sur le partage réseau.** Écrire du HDF5 directement sur un partage SMB pose des problèmes de verrouillage, et une coupure réseau peut corrompre le fichier. Donc :
  - écrire le fichier dans un dossier local du PC d'acquisition (configurable, `IRLAB_LOCAL_DATA_DIR`) ;
  - à la fin du scan, quel que soit le statut, le copier vers le dossier partagé (`IRLAB_DATA_DIR`, qui pointe par exemple vers `\\pc-pilote\data`, avec un chemin UNC et non une lettre de lecteur) ;
  - si la copie échoue, garder le fichier local, afficher un avertissement clair, et fournir une fonction `sync_data()` qui recopie les fichiers locaux absents du partage.
- **Nommage et dossier.** Nom de fichier : `AAAA-MM-JJ/scan_NNNN.h5`, où le numéro de scan est incrémenté automatiquement sans écraser de fichier existant, ni en local ni sur le partage.
- **Fin de scan.**
  - Afficher la progression (point i/N, position, temps restant estimé).
  - En fin de scan, afficher le chemin du fichier.
  - Respecter les tâches 3 et 4 : arrêt propre en cas d'erreur ou de Ctrl+C. Le fichier reste valide et contient un attribut `status` qui vaut `completed`, `aborted` ou `error`.
- Supprimer l'ancienne `save_hdf5`, ou l'adapter pour qu'elle utilise ce nouveau format.
- Prévoir dans l'interface la possibilité d'un scan à 2 dimensions plus tard (`mesh`), mais **ne pas l'implémenter** maintenant.

**Test sur le banc.** `ascan(sx, 0, 1, 11, exposure=0.1)` produit un fichier HDF5 avec 11 spectres et toutes les métadonnées, présent en local et sur le partage. Un Ctrl+C au 5e point laisse un fichier lisible avec `status=aborted` et 5 points. Un scan lancé avec le partage inaccessible garde le fichier en local, et `sync_data()` le recopie une fois le partage revenu.

---

## 14. Mouvements simultanés dans `mv` (fonctionnel)

**Pourquoi.** `mv(m1, p1, m2, p2)` déplace les moteurs l'un après l'autre, car chaque requête attend la fin du mouvement. Dans SPEC, `mv` déplace les moteurs en même temps. Bloquer la requête HTTP pendant tout le mouvement empêche aussi un arrêt propre par Ctrl+C (tâche 4).

**Fichiers.** `servers/motion_server.py`, `clients/motion_client.py`.

**À faire.**

- **Côté serveur, séparer lancer et attendre.**
  - `POST /motors/start_move_abs/{motor}` et `POST /motors/start_move_rel/{motor}` lancent le mouvement et rendent la main tout de suite.
  - Le suivi du mouvement (attente, vérification de la position finale, délai maximal) se fait dans un thread du serveur, par moteur.
  - `GET /motors/state/{motor}` renvoie l'état : `idle`, `moving`, `error` (avec le message) ou `stopped`, ainsi que la position.
  - Garder un endpoint bloquant `POST /motors/move_abs/{motor}` pour les usages simples. Il peut s'appuyer sur les deux précédents.
- **Côté client.**
  - `mv()` lance tous les mouvements, puis attend en interrogeant l'état toutes les 0,1 s environ (interruptible, pour la tâche 4).
  - Il lève une `MotionError` si un des moteurs finit en erreur.
  - Le paramètre `sequential=False` (simultané par défaut) permet de revenir à l'ancien comportement.
  - Faire de même pour `mvr()`.
- **Mouvements simultanés sur un même PS90.** Si deux moteurs du même contrôleur bougent en même temps, vérifier que la boucle de suivi partage correctement le verrou série de la tâche 1.

**Test sur le banc.** `mv(sx, a, sy, b)` déplace les deux axes en même temps, et la durée totale est celle du plus long mouvement. Un Ctrl+C pendant l'attente arrête les deux moteurs.

---

## 15. Petits bugs et nettoyage (qualité)

**Fichiers concernés :** `servers/festo_server.py`, `servers/motion_server.py`, `clients/motion_client.py` et `clients/festo_client.py`.

**`servers/festo_server.py`**

- **`festo_close()`, lignes 240–243.** La boucle de suppression des actionneurs teste `a.controller is not controllers.get(name)` après avoir déjà supprimé `controllers[name]`. La logique ne fonctionne que par accident. La réécrire simplement : garder une référence au contrôleur fermé, puis supprimer les actionneurs qui pointent vers lui.
- **Défaut du nom de contrôleur.** `festo_connect()` utilise le nom par défaut `festo`, alors que le YAML utilise `main_festo`. Harmoniser, ou documenter.

**`servers/motion_server.py`**

- **`PS90.read()`** est vide et inutilisée : la supprimer.
- **`PS90_motor.initialize_axis()`** contient des `except:` nus et des `print` avec des fautes (« initilaize moto »). Utiliser `except Exception` et le logger, et propager l'erreur.
- **`read_parameters()`** fait des `print` côté serveur, donc invisibles pour le client. La transformer en endpoint `GET /motors/parameters/{motor}` qui renvoie un dict.
- **Vitesse et accélération** (`PVEL`, `ACC`) : elles sont appliquées à l'enregistrement, mais les erreurs sont ignorées en silence. Les journaliser.
- **Port série par défaut** : `/dev/ttyUSB0` d'un côté, `COM25` de l'autre. Le système étant sous Windows, un seul défaut, et de préférence aucun : le port doit venir de la config.
- **Port série déjà ouvert** : si le port est déjà ouvert par un autre processus (deuxième instance du serveur), afficher un message clair au lieu de l'erreur brute de pyserial.

**`clients/motion_client.py`**

- **Orthographe des attributs.** `Motor` utilise `controler_type` et `controler_channel` (un seul « l »), mais `controller_name` (deux « l »). Renommer en `controller_type` et `controller_channel`, et garder les anciens noms comme propriétés dépréciées pour ne pas casser les scripts existants. Côté YAML, accepter l'ancienne orthographe en lecture, mais documenter la nouvelle seulement.
- **Unités dans `mv()`.** Aujourd'hui, une position est lue en millimètres si c'est un `float` **ou** si `step_to_mm != 1.0`, et en pas sinon. C'est implicite et piégeux : `mv(m, 2)` et `mv(m, 2.0)` ne font pas la même chose sur un moteur non calibré. Clarifier :
  - chaque moteur a une unité utilisateur explicite dans le YAML (`unit: mm`, ou `steps`, `deg`…) ;
  - `mv` interprète toujours la valeur dans cette unité ;
  - documenter le comportement.
- **Doublon dans `wm()`.** `wm()` renvoie un dict `{'steps', 'mm'}` qu'il faut ensuite déballer partout (`_extract_wm_value`, `ascan`…). Ajouter une méthode `Motor.position()` qui renvoie directement la valeur dans l'unité utilisateur, et l'utiliser dans les scripts. Garder `wm()` pour l'affichage.
- **Doublons de code.** Les fonctions `free` et `control`, ou `free_all_motors` et `control_all_motors`, sont presque identiques. Factoriser avec une fonction interne.
- **Méthodes manquantes sur `Motor`.** Ajouter des méthodes `move()`, `move_rel()`, `position()` et `stop()`, comme `PneumaticActuator` a déjà `on()` et `off()`, ainsi qu'un `__repr__` qui affiche le nom, la position et l'unité.

**`clients/festo_client.py`**

- **Doublons de code.** Les fonctions `on`, `off` et `toggle` sont presque identiques. Factoriser avec une fonction interne.

**Test sur le banc.** Les commandes habituelles du shell (`mv`, `mvr`, `wm`, `free`, `control`, `on`, `off`, `toggle`, `state`, `tweak`) fonctionnent comme avant. `mv(m, 2)` et `mv(m, 2.0)` donnent le même résultat.

---

## 16. Versions figées et installation hors ligne (déploiement)

**Pourquoi.** Le réseau du banc n'a pas Internet, et `requirements.txt` n'indique aucune version. Une réinstallation pourrait donc donner des versions différentes, ou être impossible.

**Fichiers.** `requirements.txt`, nouveau dossier `tools/`, `README.md`.

**À faire.**

- **Figer les versions** dans `requirements.txt` (`==`).
  - Ne pas choisir les versions au hasard : ajouter dans le README la consigne de lancer `pip freeze` dans le `.venv` d'un PC du banc qui fonctionne, et de reporter ces versions.
  - Indiquer la version de Python utilisée.
- **Script `tools/download_wheels.ps1`** à lancer sur une machine connectée à Internet. Il fait :
  ```
  pip download -r requirements.txt -d wheels/ --platform win_amd64 --python-version <ver> --only-binary=:all:
  ```
- **Script `tools/install_offline.ps1`** à lancer sur un PC du banc. Il :
  - crée le `.venv` ;
  - installe avec `pip install --no-index --find-links wheels/ -r requirements.txt` ;
  - vérifie l'import des modules.
- Ajouter `wheels/` au `.gitignore`.
- **NI-DAQmx** nécessite aussi le pilote NI installé sur la machine, en plus du paquet Python. Le documenter dans le README.

**Test sur le banc.** Sur un PC du banc, supprimer et recréer le `.venv` avec `install_offline.ps1`, sans Internet : les serveurs et le shell redémarrent normalement.

---

## 17. Scripts de démarrage et documentation (déploiement)

**Fichiers.** `start_*.ps1`, `README.md`.

**À faire.**

- **Rendre les scripts de démarrage robustes.**
  - Se placer dans le dossier du dépôt (`Set-Location $PSScriptRoot`), pour pouvoir les lancer depuis n'importe où.
  - Vérifier que le `.venv` existe, et afficher un message clair sinon.
  - Lancer `python -m uvicorn` avec le Python du `.venv`, plutôt que de dépendre de l'activation.
- **Documenter en option le lancement automatique** au démarrage de Windows, via une tâche planifiée ou NSSM. Le documenter seulement, sans l'imposer.
- **Mettre à jour le README** :
  - architecture : quel serveur sur quel PC ;
  - installation hors ligne ;
  - démarrage ;
  - liste des endpoints après la tâche 11 ;
  - commandes du shell, y compris `stop`, `stop_all`, `reconnect` et `sync_data` ;
  - format des fichiers HDF5 et circuit local → partage ;
  - variables d'environnement (`IRLAB_DATA_DIR`, `IRLAB_LOCAL_DATA_DIR`, `IRLAB_LOG_DIR`, `IRLAB_MOTORS_CONFIG`, `IRLAB_FESTO_CONFIG`, `MOTION_SERVER`…) ;
  - section « Points à vérifier sur le matériel » qui reprend tous les `À VÉRIFIER`.
- **Pare-feu.** Les ports 8001 à 8003 doivent être ouverts en entrée sur les PC serveurs, et uniquement depuis le sous-réseau du banc. Le documenter avec la commande :
  ```powershell
  New-NetFirewallRule -DisplayName "IRLab servers" -Direction Inbound -Protocol TCP -LocalPort 8001-8003 -RemoteAddress <sous-réseau>/24 -Action Allow
  ```

---

## Annexe : tests

Pas de mode simulation dans le code de production. Seuls les tests automatiques légers suivants sont autorisés :

- **Dossier `tests/`**, avec `pytest`, et un fichier `requirements-dev.txt` (`pytest`, `httpx`).
- **Faux port série (`tests/fake_serial.py`).** Un petit objet qui imite `serial.Serial` (`write`, `read_until`, `reset_input_buffer`, `close`) et répond aux quelques commandes PS90 utilisées : `?CNT`, `?ASTAT`, `PSET`, `PGO`, plus la commande d'arrêt. Il est injecté dans les tests par `monkeypatch` sur `serial.Serial`. **Aucune modification des serveurs** ne doit être faite pour l'accueillir.
- **Couverture visée** : le verrou série (tâche 1, requêtes concurrentes), la gestion des réponses lentes ou tronquées (tâche 2), la remontée des erreurs (tâche 3), l'arrêt (tâche 4) et le mouvement relatif (tâche 5).
- **Si ce faux port devient complexe** (plus d'environ 100 lignes), s'arrêter là : ces tests servent de filet de sécurité, ils ne remplacent pas les tests sur le banc.

---

## Hors périmètre (ne pas faire maintenant)

- Mode simulation des serveurs (moteurs, FESTO). Le spectromètre simulé actuel reste tel quel.
- Authentification et chiffrement entre clients et serveurs : le réseau est isolé, et ce n'est pas la priorité.
- Interface graphique.
- Migration vers Bluesky, Ophyd ou Tango.
- Intégration réelle du SDK Andor, qui sera faite à part avec le matériel.
- Scans à 2 dimensions (`mesh`) : prévoir l'interface, ne pas implémenter.

---

## Résumé attendu en fin de travail

1. La liste des tâches faites, avec le hash de commit de chacune.
2. Les points `À VÉRIFIER` sur le matériel (protocole PS90, NI-DAQmx), avec le fichier et la ligne de chacun.
3. Les changements qui cassent la compatibilité, et ce qu'il faut adapter dans les scripts utilisateurs existants.
4. La liste des tests sur le banc, dans l'ordre où les faire : moteurs un par un à faible vitesse, arrêt d'urgence, puis scans.
