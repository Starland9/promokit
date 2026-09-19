# Bibliothèque de prompts H3 « motion design 2D » (série de concepts)

Fichiers prêts à copier dans `projects/<projet>/prompts/`. Chaque fichier respecte le format officiel MiniMax (skill `h3-prompting`).
`md_*` sont des prompts T2VA (ancre de style) ; pour les clips suivants d'une même vidéo, prendre `ref2va_style.txt`
et coller la chorégraphie du `md_*` voulu dans `detailed_description` (image de référence = frame du clip d'ancrage).
Bloc de style commun : garder mot pour mot, changer seulement la dominante (`blue` → `red`/`green`/`amber`) et la chorégraphie.

| Fichier | Concept type | Chorégraphie |
|---|---|---|
| md_person_hook | accroche vécue | une personne, une réaction (documentaire, pas de motion design) |
| md_flow | requête/réponse, API, HTTP, webhook | client ↔ serveur, paquets sur un connecteur |
| md_secure | HTTPS, TLS, hachage, JWT, secrets | tunnel, bouclier, cadenas, paquet illisible |
| md_database | index, N+1, transactions, migrations | table de lignes, curseur, requête lente puis rapide |
| md_cache | cache, TTL, CDN, Redis | raccourci lumineux, tuile qui expire |
| md_queue | message queue, jobs, retry, pub/sub | file de tuiles, producteur/consommateurs |
| md_versus | REST vs GraphQL, SQL vs NoSQL, session vs JWT | deux colonnes, curseur de décision |
| md_error | panne, 5xx, timeout, injection | rouge, glitch, fragments |
| md_success | résolution, bonne pratique | vert, alignement, coche |
| md_architecture | monolithe, microservices, gateway, hexagonale | blocs qui se scindent ou s'assemblent |
| md_numbers | codes HTTP, chiffres clés | chiffres géants néon (les chiffres sont fiables, pas les mots) |
