"""Les deux `ClientLLM` du harnais : celui qui rejoue, celui qui enregistre.

**Ce module ne charge pas le SDK**, et ce n'est pas une coquetterie : c'est ce qui fait
que `make eval` tourne **sans clé API**. Le rejeu n'a besoin que d'un fichier et du
`Protocol` `ClientLLM` — exactement la couture que la docstring de `agent/client.py`
annonçait, et le troisième usage qu'elle achète après le faux client de l'étape 8 et les
`dependency_overrides` de l'étape 10.

`ClientEnregistreur`, lui, **enveloppe** un `ClientLLM` quelconque : c'est l'appelant qui
lui passe un `ClientAnthropic`, et l'import du SDK reste dans `scripts/eval.py`.

---

### Rejeu par index, avec assertion d'empreinte (arbitrage B)

On rend la n-ième prise, comme le `FauxClient` de l'étape 8 — mais on **vérifie d'abord**
que l'empreinte de la requête reçue est celle enregistrée. Un écart fait échouer le
scénario **en nommant le tour où la conversation a divergé**, avec un diff lisible.

*Alternative écartée — l'index seul.* Une divergence **désynchronise en silence** : le
modèle reçoit la réponse du tour suivant, la conversation part ailleurs, et les métriques
décrivent une conversation qui n'a jamais eu lieu. C'est le mode d'échec le plus coûteux
d'un harnais d'éval, parce qu'il produit **des chiffres au lieu d'une erreur**.

*Alternative écartée — un dictionnaire indexé par empreinte.* Robuste à un
réordonnancement, mais le message d'échec parlerait d'un hash absent au lieu d'un tour, et
une cassette lue hors ordre ne se relit pas à la main.

### Ce qui rend une cassette périmée est vérifié **avant** le premier tour

`verifier()` compare les trois empreintes de l'en-tête à celles en vigueur. Échouer au
premier tour plutôt qu'à la construction dirait « la conversation a divergé » là où la
vraie cause est « le prompt a changé » — deux diagnostics très différents pour la même
personne, un mardi soir.
"""

import difflib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from raiyon.agent.client import ClientLLM, ReponseLLM
from raiyon.eval.cassette import (
    COMMANDE_DE_REGENERATION,
    Cassette,
    CassetteEpuisee,
    CassettePerimee,
    DivergenceDeRequete,
    EnTete,
    Prise,
    apercu_de_requete,
    empreinte_de_requete,
)

LIGNES_DE_DIFF = 40
"""Le diff d'une divergence est tronqué : au-delà, il cesse d'aider à lire l'écart."""


def verifier(
    cassette: Cassette,
    *,
    prompt_version: str,
    prompt_empreinte: str,
    outils_empreinte: str,
    source: str | None = None,
) -> None:
    """Les trois empreintes de l'en-tête, contre celles en vigueur (arbitrage C).

    L'empreinte du **schéma d'outils** est celle que la formulation « hash du prompt » du
    §5 laissait échapper : le schéma fait partie du préfixe mis en cache et détermine ce
    que le modèle peut faire. Un outil dont la description change rend la cassette aussi
    périmée qu'un prompt modifié.

    §3.15 annonçait « une discipline à tenir » ; ici, ce n'est plus une discipline.

    ### `source` nomme le répertoire, et depuis l'étape 13 ce n'est plus du confort

    Les cassettes vivent dans `evals/cassettes/<version>/`, une par version de prompt. Le
    mode d'échec neuf est donc **une cassette rangée dans le mauvais répertoire** — un
    fichier v2 déposé sous `systeme.v1/`, par un `git mv` ou une campagne lancée sans sa
    variable. L'empreinte le détecte déjà ; mais « cassette a1b2, en vigueur c3d4 » envoie
    chercher un prompt modifié là où la faute est un fichier mal rangé, et les deux se
    corrigent à deux endroits opposés. Le message nomme donc le chemin **et** les deux
    versions, celle que la cassette déclare et celle qui tourne.
    """
    ecarts: list[str] = []
    if cassette.entete.prompt_empreinte != prompt_empreinte:
        ecarts.append(
            f"prompt système : la cassette déclare {cassette.entete.prompt_version} "
            f"({cassette.entete.prompt_empreinte}), en vigueur {prompt_version} "
            f"({prompt_empreinte})"
        )
    if cassette.entete.outils_empreinte != outils_empreinte:
        ecarts.append(
            f"schéma d'outils : cassette {cassette.entete.outils_empreinte}, "
            f"en vigueur {outils_empreinte}"
        )
    if not ecarts:
        return
    situation = source or f"{cassette.entete.scenario}.{cassette.entete.prise}"
    raise CassettePerimee(
        f"la cassette {situation} est périmée :\n"
        + "\n".join(f"  - {ecart}" for ecart in ecarts)
        + "\n\nElle a été enregistrée contre un autre préfixe : la rejouer mesurerait "
        "un produit qui n'existe plus.\n\nDeux causes, et elles se corrigent à deux "
        "endroits opposés :\n"
        "  - le prompt en vigueur a changé      → régénérer (commande ci-dessous) ;\n"
        "  - le fichier est dans le mauvais jeu → le déplacer sous "
        f"evals/cassettes/{cassette.entete.prompt_version}/.\n\nRégénérer :\n    "
        + COMMANDE_DE_REGENERATION.format(version=prompt_version, scenario=cassette.entete.scenario)
    )


@dataclass
class ClientCassette:
    """Rejoue une cassette, prise par prise, et refuse de deviner.

    `source` n'est là que pour les messages d'erreur : sur seize cassettes, savoir
    **laquelle** a divergé est la moitié du diagnostic.
    """

    cassette: Cassette
    source: str
    index: int = 0

    @property
    def epuisee(self) -> bool:
        return self.index >= len(self.cassette.prises)

    def repondre(
        self,
        *,
        systeme: str,
        outils: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ReponseLLM:
        """La prise suivante — après avoir constaté que c'est bien la bonne requête."""
        if self.epuisee:
            raise CassetteEpuisee(
                f"{self.source} porte {len(self.cassette.prises)} prise(s) et la boucle "
                f"en demande une de plus.\nLa conversation rejouée est plus longue que "
                "celle enregistrée — le moteur, la couche outils ou le validateur ont "
                "changé de comportement (arbitrage A : eux ne sont pas enregistrés).\n"
                "Régénérer :\n    "
                + COMMANDE_DE_REGENERATION.format(
                    version=self.cassette.entete.prompt_version,
                    scenario=self.cassette.entete.scenario,
                )
            )

        prise = self.cassette.prises[self.index]
        recue = empreinte_de_requete(systeme=systeme, outils=outils, messages=messages)
        if recue != prise.requete:
            raise DivergenceDeRequete(self._message_de_divergence(prise, messages, recue))

        self.index += 1
        return prise.en_reponse()

    def _message_de_divergence(
        self,
        prise: Prise,
        messages: Sequence[dict[str, Any]],
        recue: str,
    ) -> str:
        """Nomme le tour, puis montre l'écart. Dans cet ordre : le tour est l'information.

        Le diff porte sur l'`apercu` — une ligne par message — et non sur le JSON brut :
        c'est ce qui rend lisible « le `tool_result` du tour 2 ne dit plus la même chose »
        au lieu d'un mur de trois mille caractères.
        """
        diff = difflib.unified_diff(
            list(prise.apercu),
            list(apercu_de_requete(messages)),
            fromfile="enregistré",
            tofile="reçu",
            lineterm="",
            n=1,
        )
        lignes = list(diff)[:LIGNES_DE_DIFF]
        return (
            f"{self.source} : la conversation a divergé au tour {self.index + 1} "
            f"(prise {self.index + 1} sur {len(self.cassette.prises)}).\n"
            f"  empreinte enregistrée : {prise.requete}\n"
            f"  empreinte reçue       : {recue}\n\n"
            "Rendre la prise suivante quand même désynchroniserait la conversation en "
            "silence, et les métriques\ndécriraient un dialogue qui n'a jamais eu lieu. "
            "Voici l'écart :\n\n" + "\n".join(lignes) + "\n\nSi le changement est voulu, "
            "régénérer :\n    "
            + COMMANDE_DE_REGENERATION.format(
                version=self.cassette.entete.prompt_version,
                scenario=self.cassette.entete.scenario,
            )
        )


@dataclass
class ClientEnregistreur:
    """Enveloppe un `ClientLLM` réel et note ce qu'il répond. **Rien d'autre.**

    Pas de `tool_result`, pas d'état, pas de produits (arbitrage A) : ils sont recalculés
    au rejeu par le vrai moteur, sur le seed committé. C'est ce qui fait que l'éval mesure
    la pile entière et non la conduite du dialogue contre un passé figé.
    """

    reel: ClientLLM
    prises: list[Prise] = field(default_factory=list)

    def repondre(
        self,
        *,
        systeme: str,
        outils: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> ReponseLLM:
        """L'empreinte et l'aperçu sont pris **avant** l'appel.

        La boucle continue d'allonger `messages` après le retour ; les calculer ensuite
        enregistrerait la requête du tour suivant, et la cassette ne se rejouerait
        jamais — c'est le piège que `FauxClient` documente déjà pour ses assertions.
        """
        empreinte = empreinte_de_requete(systeme=systeme, outils=outils, messages=messages)
        apercu = apercu_de_requete(messages)
        reponse = self.reel.repondre(systeme=systeme, outils=outils, messages=messages)
        self.prises.append(
            Prise(
                requete=empreinte,
                apercu=apercu,
                blocs=[dict(bloc) for bloc in reponse.blocs],
                fin=reponse.fin,
            )
        )
        return reponse

    def en_cassette(self, entete: EnTete) -> Cassette:
        return Cassette(entete=entete, prises=tuple(self.prises))


_: type[ClientLLM] = ClientCassette
__: type[ClientLLM] = ClientEnregistreur
"""Deux annotations qui ne servent qu'à `mypy` : elles font échouer `make typecheck` si
l'un des deux clients cesse de satisfaire le `Protocol`. C'est le même geste que
l'`assert_never` de `serialisation.py` — l'exhaustivité vérifiée, pas relue."""
