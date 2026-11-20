# Modules

Each MechFrame module this site has, copied in by `mechframe add <id>` as `<id_>/` (its id with `_` for `-`): its backend package, `module.json`, `MODULE.md` and `CHANGELOG.md`. Its migrations sit in `../migrations/<id>/` and its web binding in `web/src/modules/<id>/`.

These folders are MechFrame's. Change one only when its settings, slots and events can't do what the site needs: `mechframe check` reports every edit against `mechframe.lock.json`.
