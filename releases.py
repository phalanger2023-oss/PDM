"""Notes de version de l'éditeur PDF : source unique de l'historique affiché sur le site.

RÈGLE : une seule mise à jour PAR JOUR. Si plusieurs modifications sont livrées le même jour, elles sont
regroupées dans la même entrée (la plus récente, en tête) et la version n'est incrémentée qu'une fois.
Une nouvelle entrée n'est créée que pour un nouveau jour (ou si l'utilisateur le demande expressément).
Catégories : nouveautes, ameliorations, corrections. `date` : AAAA-MM-JJ (None si inconnue).
"""

RELEASES = [
    {
        "version": "1.2.0", "date": "2026-11-22",
        "nouveautes": [
            "Dossiers : les documents déposés par DeepWell sont rangés par dossier (année / matière / chapitre). Un filtre « Tous les dossiers » apparaît sur l'accueil, le dossier est affiché sur chaque carte et la recherche en tient compte.",
            "Lien avec DeepWell : sur l'accueil, « Lier à DeepWell » affiche la clé secrète à recopier dans DeepWell (Réglages → Google Drive → PDM). Avec cette clé, DeepWell dépose tout seul les documents de référence de tes cours. La clé ne permet pas de se connecter au site ; « Nouvelle clé » annule l'ancienne.",
            "Le PDF d'origine (jamais modifié) peut être téléchargé tel quel, adresse « …/api/docs/NOM/pdf?dl=1 » : c'est le lien « document vierge » donné par DeepWell.",
        ],
        "ameliorations": [
            "La liste de l'accueil n'est plus limitée à 60 documents (1000 maximum).",
        ],
        "corrections": [],
    },
    {
        "version": "1.1.0", "date": "2026-11-20",
        "nouveautes": [
            "Les formules et caractères spéciaux (qui ne pouvaient pas être touchés) sont maintenant déplaçables et supprimables, avec une copie nette. Ils ne sont pas modifiables.",
            "Les images utilisées plusieurs fois dans le PDF (logos, puces…) peuvent maintenant être sélectionnées, déplacées et supprimées.",
            "Les traits, cadres, tableaux et formes peuvent maintenant être déplacés et supprimés.",
            "Nouveau thème « Noir profond », choix de la police, réglage de l'arrondi des coins et CSS personnalisé dans les réglages, comme sur DeepWell.",
            "Les notes de version sont maintenant disponibles depuis l'accueil.",
        ],
        "ameliorations": [
            "L'apparence de l'éditeur est alignée sur celle de DeepWell (couleurs, bordures fines, police, coins).",
            "Un numéro suivi d'un titre (« 1.2  Introduction ») reste maintenant sur une seule ligne avec sa mise en page d'origine quand on le modifie.",
        ],
        "corrections": [],
    },
    {
        "version": "1.0.0", "date": None,
        "nouveautes": [
            "Version de départ : annotations, surlignage, modification du texte et des images du PDF, enregistrement automatique.",
        ],
        "ameliorations": [],
        "corrections": [],
    },
]
VERSION = RELEASES[0]["version"]
