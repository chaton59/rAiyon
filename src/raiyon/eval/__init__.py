"""Le harnais d'éval : cassettes, scénarios, métriques, rapport.

Quatre modules sont **purs** — `cassette`, `scenario`, `metriques`, `rapport` — et un
cinquième l'est par surcroît, `client` : rejouer une cassette ne charge pas le SDK. C'est
ce qui fait que `make eval` tourne **sans clé API**, et un test le vérifie sur le disque.

Ce que le paquet ne contient pas, et c'est l'arbitrage A : aucun `tool_result` enregistré.
Une cassette ne porte que les réponses du modèle ; tout le reste — moteur, couche outils,
validateur — est **recalculé** au rejeu, sur le seed committé. C'est ce qui fait que
l'éval mesure la pile entière et non la conduite du dialogue contre un passé figé.
"""
