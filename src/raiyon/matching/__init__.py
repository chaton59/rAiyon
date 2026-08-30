"""Moteur de matching — la seule partie entièrement déterministe du projet.

`SQL décide qui est candidat, Python décide comment on le présente` (PROJET.md §3.16).
La conséquence est le critère d'acceptation nº5 : hors du dépôt, tout est pur, et la
suite `tests/matching/` tourne sans base ni clé API.
"""
