"""Prépare les réglages de connexion du site (identifiant, mot de passe haché, clé secrète).

Usage (sur votre PC) :
    python outils/mot_de_passe.py

Le mot de passe n'apparaît pas à l'écran et n'est jamais enregistré : seule sa version « hachée »
(illisible, non réversible) est affichée. Copiez les trois lignes obtenues dans le fichier .env du serveur.
Relancer l'outil produit de nouveaux réglages : cela déconnecte tous les appareils.
"""
import getpass
import secrets
import sys

MIN_LONGUEUR = 12


def lignes_env(identifiant, mot_de_passe):
    """Renvoie les trois lignes AUTH_USER / AUTH_HASH / SECRET_KEY prêtes à coller dans .env."""
    import bcrypt  # importé ici pour pouvoir expliquer clairement s'il manque

    if not identifiant or ":" in identifiant or " " in identifiant or "'" in identifiant:
        raise ValueError("L'identifiant ne doit être ni vide, ni contenir d'espace, de « : » ou d'apostrophe.")
    if len(mot_de_passe) < MIN_LONGUEUR:
        raise ValueError(f"Le mot de passe doit faire au moins {MIN_LONGUEUR} caractères.")
    if len(mot_de_passe.encode()) > 72:
        raise ValueError("Le mot de passe est trop long (72 octets maximum pour bcrypt).")
    hache = bcrypt.hashpw(mot_de_passe.encode(), bcrypt.gensalt(rounds=12)).decode()
    hache = "$2y$" + hache[4:]  # même algorithme, préfixe usuel des mots de passe hachés
    return (
        f"AUTH_USER={identifiant}\n"
        f"AUTH_HASH='{hache}'\n"          # apostrophes obligatoires : elles protègent les « $ »
        f"SECRET_KEY={secrets.token_hex(32)}"
    )


def main():
    try:
        import bcrypt  # noqa: F401
    except ImportError:
        print("Il manque la bibliothèque « bcrypt ». Tapez d'abord :  pip install bcrypt")
        return 1
    identifiant = input("Identifiant : ").strip()
    mdp = getpass.getpass(f"Mot de passe (au moins {MIN_LONGUEUR} caractères, invisible) : ")
    if mdp != getpass.getpass("Confirmez le mot de passe : "):
        print("Les deux mots de passe sont différents.")
        return 1
    try:
        lignes = lignes_env(identifiant, mdp)
    except ValueError as e:
        print(e)
        return 1
    print("\nCopiez ces trois lignes dans le fichier .env du serveur (à la place des anciennes lignes AUTH_*, SECRET_KEY) :\n")
    print(lignes)
    print("\nLa SECRET_KEY et le hachage sont des secrets : ne les partagez pas et ne les envoyez à personne.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
