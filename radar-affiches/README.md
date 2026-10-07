# Radar Affiches

Surveille la programmation UGC (C2L Poissy), détecte les films qui disparaissent de la semaine suivante,
t'envoie une notification (ntfy) et affiche tout dans une petite app installable (PWA) avec ta collection d'affiches.

- `radar/` : connecteur UGC, détection, notifications, tâche automatique
- `docs/` : l'app mobile (publiée par GitHub Pages) + `data.json` (généré)
- `data/state.json` : historique des relevés (généré)
- `config.json` : cinémas et créneaux de récupération (modifiable)
- `.github/workflows/radar.yml` : lancement automatique 6 fois par jour

Test local : `python scan.py` (relevé + comparaison à l'écran) · `python -m radar.run` (cycle complet).
