# Tests physiques à réaliser sur le banc

Tests à faire après les modifications de la branche `reliability-improvements`.
Chaque section correspond à une tâche de `IRLab_modifications.md` et à un commit :
en cas de problème, on peut revenir en arrière tâche par tâche.

Cocher chaque test une fois validé, et noter le résultat en cas d'échec.

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

- [ ] **Avant tout : vérifier dans le manuel OWIS PS90** (points marqués `À VÉRIFIER` dans `servers/motion_server.py`) :
  - le caractère de fin de réponse (`PS90_TERMINATOR`, supposé `\r`). Si c'est faux, **toutes** les lectures échoueront en timeout ;
  - le délai minimal entre deux commandes (`PS90_DEFAULT_COMMAND_DELAY`, laissé à 0,05 s comme avant). Réglable par contrôleur avec `command_delay` dans `config/motors.yaml`.
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
  *Attendu :* `mv()` lève une `MotionError` qui indique le moteur, la consigne, la position atteinte et le caractère d'état de l'axe (`axis status`). **Noter ce caractère d'état** (signification à rapprocher du manuel PS90).
- [ ] **Scan qui traverse la limite.** `ascan()` sur ce même axe, avec des points au-delà de la fin de course.
  *Attendu :* le scan s'arrête au premier point en erreur, affiche « Scan stopped at point i/N », et **ne ramène pas** le moteur à sa position initiale (message « NOT returned »).
- [ ] **Délai maximal.** Dans `config/motors.yaml`, mettre temporairement `max_move_duration: 2` sur un moteur, redémarrer le serveur moteurs, puis lancer un mouvement qui dure plus de 2 s, **à faible vitesse**.
  *Attendu :* l'axe est arrêté au bout de 2 s et `mv()` lève une `MotionError` « move not finished after 2.0 s, stop sent ». Ce test vérifie aussi la commande d'arrêt (`PS90_STOP_AXIS_CMD`, voir tâche 4). Remettre ensuite la valeur d'origine.
- [ ] **Tolérance de position.** Si un axe s'arrête régulièrement à ±1 pas de la consigne, régler `position_tolerance_steps` dans `config/motors.yaml` pour ce moteur.

Remarques / résultats :

---

## Tâche 4 : arrêt d'urgence

⚠️ **À faire à faible vitesse, en surveillant le banc, la main près de l'arrêt matériel.**

- [ ] **Avant tout : vérifier dans le manuel OWIS PS90** (points `À VÉRIFIER` dans `servers/motion_server.py`) :
  - la commande d'arrêt d'un axe (`PS90_STOP_AXIS_CMD`, supposée `STOP<n>`). **Si elle est fausse, aucun arrêt ne fonctionnera** : c'est à confirmer avant tous les autres tests de cette section ;
  - s'il existe une commande d'arrêt général du contrôleur : la mettre dans `PS90_STOP_ALL_CMD` (aujourd'hui `None` : `stop_all()` arrête un à un les axes des moteurs déclarés dans `config/motors.yaml`, **pas les axes non déclarés**).
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

