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

