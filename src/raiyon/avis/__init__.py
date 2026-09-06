"""Le cache des avis web : la clé, la table, et rien qui parle au réseau.

⚠️ **Aucun module de ce paquet n'appelle un fournisseur de recherche.** À l'étape 26 il
n'en existe aucun : le cache est rempli par le seed, comme le catalogue l'est déjà. Le
jour où un fournisseur entrera, il vivra dans **un module à lui**, et
`tests/avis/test_isolation_reseau.py` échouera si un autre module de `raiyon` se met à
charger un client HTTP.

C'est la traduction en code d'une décision, pas une précaution de style : les campagnes
d'éval ne sortent jamais sur le réseau, ni pour le coût, ni pour la clause §3(b) des
conditions Brave qui interdit d'employer des résultats de recherche pour *« evaluate […]
or benchmark »* un modèle. Un cache pré-chargé de contenus **écrits à la main** ferme les
deux d'un seul geste.
"""
