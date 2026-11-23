"""Notes de version de l'éditeur PDF : source unique de l'historique affiché sur le site.

RÈGLE : une seule mise à jour PAR JOUR. Si plusieurs modifications sont livrées le même jour, elles sont
regroupées dans la même entrée (la plus récente, en tête) et la version n'est incrémentée qu'une fois.
Une nouvelle entrée n'est créée que pour un nouveau jour (ou si l'utilisateur le demande expressément).
Catégories : nouveautes, ameliorations, corrections. `date` : AAAA-MM-JJ (None si inconnue).
"""

RELEASES = [
    {
        "version": "1.5.0", "date": "2026-11-23",
        "nouveautes": [
            "Notes de version : bouton « Crédits » (réalisé par, en partenariat avec, citation…). Le texte se remplit dans DeepWell (Notes de version → Crédits) et s'affiche ici automatiquement.",
            "Compte unique avec DeepWell : on se connecte une seule fois sur DeepWell ; en ouvrant PDM sans être connecté, tu es renvoyé vers DeepWell puis ramené ici, connecté. Chaque compte DeepWell a son propre espace de documents (tes documents actuels restent chez l'administrateur). La connexion propre à PDM reste en secours sur /login?local=1.",
            "Zone de texte façon Canva : elle grandit toute seule quand tu écris (Entrée ajoute une ligne), la barre sur chaque côté règle la largeur du texte, la poignée du haut agrandit ou réduit le texte, et le correcteur orthographique ne s'active que dans la zone sélectionnée. Une zone vide qu'on quitte disparaît.",
            "Interligne réglable (zones de texte et paragraphes du PDF), et 7 nouvelles polices intégrées au PDF final (Calibri-like, Cambria-like, Cardo, Crimson, DejaVu, Comic Relief, Anton) : ce que tu vois à l'écran est ce qui est écrit dans le PDF.",
            "Calques : « premier plan / avancer / reculer / arrière-plan » pour les zones de texte et les formes, respectés dans le PDF enregistré (un texte peut maintenant passer sous une forme).",
            "Copier, coller et dupliquer une zone de texte ou une forme (boutons, Ctrl+C, Ctrl+V, Ctrl+D).",
            "Zoom au pincement (doigts ou pavé tactile) et Ctrl + molette.",
            "Les options d'édition s'affichent dans un panneau à gauche (sur grand écran) au lieu d'une barre en haut.",
            "Menu « Plus » (⋯) : apparence, personnalisation, raccourcis, déconnexion (seulement depuis l'accueil). Nouveau logo.",
            "Accueil : l'icône choisie dans les réglages de DeepWell sert de grand fond d'écran très pâle, centré (DeepWell l'envoie tout seul à PDM à chaque changement ; sans icône choisie, logo de base). Nouvelle icône du site, très minimaliste : une simple feuille, sans fond, dans la couleur d'accent que tu as choisie (logo, accueil et onglet du navigateur).",
            "Raccourcis clavier : Ctrl+Z / Ctrl+Y (ou Ctrl+Maj+Z) annulent et rétablissent tout, même quand le curseur est dans une zone de texte ; Ctrl+C, Ctrl+X, Ctrl+V et Ctrl+D marchent pour les zones de texte, les formes, les dessins et aussi les paragraphes du PDF (copiés en nouvelle zone). Ctrl+V colle aussi un texte venu d'ailleurs dans une nouvelle zone.",
            "Couleurs favorites : à côté de chaque sélecteur de couleur, ☆ garde la couleur actuelle et ▾ ouvre tes favorites (× pour en retirer). Elles se retrouvent dans tous tes documents.",
            "Nouveau mode « Dessiner » (touche D) juste à côté de Surligner : trait à main levée avec couleur, épaisseur et gomme (un clic sur un trait l'efface). Il reste aussi dans « Forme ».",
            "Zone de texte : la poignée du haut suit maintenant la souris (tirer vers le haut agrandit, le bas reste en place), une poignée en bas fait pareil dans l'autre sens, et le petit rond en bas à droite redimensionne tout (largeur + taille du texte).",
            "Crayon : dans « Forme », nouvel outil de dessin à main levée (souris, doigt ou stylet). Le tracé se déplace, se copie, se supprime comme une forme et s'enregistre dans le PDF.",
            "Sélection multiple : Maj + clic ajoute des zones de texte et des formes à la sélection ; Ctrl+C / Ctrl+V / Ctrl+D copient ou dupliquent le groupe, Suppr l'efface (Ctrl+Z annule).",
            "Ouverture d'un document : retour à la dernière page lue ET au zoom que tu aviez, document par document.",
            "Éditeur de texte (Word) : icônes de la barre refaites en traits clairs (alignements, listes, retraits, indice/exposant, tableau…), l'outil actif (gras, liste, alignement…) est surligné, et les boutons de tableau sont explicites.",
            "Mode téléphone (menu ⋯ : automatique / activé / désactivé) : boutons plus grands, options d'édition en bandeau défilant en bas de l'écran, poignées de zone de texte agrandies pour le doigt.",
        ],
        "ameliorations": [
            "Importer un Word (.docx) garde maintenant les couleurs, tailles, polices, surlignages, l'alignement, les tableaux (cellules fusionnées), les listes et les images.",
        ],
        "corrections": [
            "Avec un fort zoom, le bord gauche de la page n'est plus coupé : on peut défiler horizontalement jusqu'à lui.",
        ],
    },
    {
        "version": "1.4.0", "date": "2026-11-22",
        "nouveautes": [
            "Documents texte, façon Word / Google Docs : sur l'accueil, « Nouveau document texte » ouvre une feuille blanche à écrire. Ils sont rangés dans les mêmes dossiers que tes PDF (vignette, renommer, déplacer, supprimer, glisser-déposer).",
            "Mise en forme : styles (Titre 1 à 3, citation), police, taille, gras / italique / souligné / barré, exposant / indice, couleur du texte et surlignage, alignement, listes à puces et numérotées, retraits, liens, images, tableaux (ajout / suppression de lignes et colonnes), ligne de séparation, annuler / rétablir. Enregistrement automatique (Ctrl+S pour forcer).",
            "Exporter : PDF, Word (.docx), ou « Créer un PDF à annoter dans PDM » (le PDF arrive dans le même dossier ; le document texte reste modifiable).",
            "Importer un fichier Word (.docx) depuis l'accueil pour le modifier ici.",
        ],
        "ameliorations": [
            "Modifier un texte natif du PDF : la couleur propre à un mot (mot en rouge dans un texte noir) est conservée, et la police d'origine du PDF est réutilisée quand elle contient toutes les lettres du texte (même rendu qu'à l'origine). Si une lettre manque dans la police (les PDF n'embarquent que les lettres utilisées), la police standard la plus proche est utilisée pour tout le style, sans mélange dans une même ligne.",
            "Performances : les fichiers du site (scripts, styles, PDF.js) sont compressés et mis en cache ; l'accueil ne rouvre plus chaque PDF pour compter ses pages (mémorisé tant que le fichier ne change pas) ; serveur réglé pour plus de stabilité (recyclage périodique des processus).",
        ],
        "corrections": [],
    },
    {
        "version": "1.3.0", "date": "2026-11-22",
        "nouveautes": [
            "Accueil en dossiers, façon écran d'accueil : des dossiers et des documents côte à côte, des dossiers dans des dossiers, autant que tu veux. Bouton « Nouveau dossier », fil d'Ariane cliquable pour remonter.",
            "Ranger : glisse un document ou un dossier sur un dossier (ou sur le fil d'Ariane), ou utilise le menu ⋯ → « Déplacer vers… » (idéal au doigt). Les dossiers se renomment, se déplacent et se suppriment : supprimer un dossier ne supprime jamais son contenu, il remonte d'un niveau.",
            "Un dossier « Scolaire » existe d'office : DeepWell y range les cours (Scolaire / année / matière / chapitre). Les documents déjà déposés par DeepWell y sont rangés automatiquement.",
            "Un PDF ouvert depuis l'accueil arrive dans le dossier que tu regardes. Les dossiers vides restent affichés.",
        ],
        "ameliorations": [
            "La recherche de l'accueil cherche dans tous les dossiers (documents et dossiers) ; le filtre « Tous les dossiers » est remplacé par la navigation.",
        ],
        "corrections": [],
    },
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
