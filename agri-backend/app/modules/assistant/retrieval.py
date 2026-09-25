"""Recherche des fiches pertinentes pour une question (sans service externe).

Score simple par mots communs (titre compté double). Suffisant pour quelques centaines de fiches ;
au-delà, passer à une recherche par vecteurs.
"""
import re
import unicodedata

STOPWORDS = set("""
a au aux avec ce ces cet cette comment dans de des du elle en est et il je la le les leur ma mais me mes mon ne
nous on ou par pas pour qu que quel quelle quels qui sa se ses son sur ta te tes ton tu un une vos votre vous y
faire fait peut puis dois doit quoi quand combien est-ce mon ma mes plante plantes champ champs
""".split())


def tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]{3,}", text)
    return {w.rstrip("s") for w in words if w not in STOPWORDS}


def rank(question: str, guides: list[dict], limit: int = 3) -> list[dict]:
    q = tokens(question)
    scored = []
    for g in guides:
        body = " ".join([g.get("summary", ""), " ".join(g.get("steps") or []), g.get("content", ""), " ".join(g.get("crops") or [])])
        score = 2 * len(q & tokens(g["title"])) + len(q & tokens(body))
        if score:
            scored.append((score, g))
    scored.sort(key=lambda x: -x[0])
    return [g for _, g in scored[:limit]]
