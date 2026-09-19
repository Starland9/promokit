---
name: tiktok-learning
description: "Produire une vidéo TikTok pédagogique (un concept expliqué en 35-60 s) avec promokit : accroche, script, direction artistique lisible sur téléphone, clips MiniMax H3 en motion design 2D cohérents, habillage, calage des pastilles sur les mots de la voix, QC. Utiliser pour la série « 100 Concepts Backend », toute vidéo « concept expliqué / vulgarisation / tuto court », ou dès qu'on parle de hook, script TikTok, motion design, slides de concept."
---

# Vidéo pédagogique TikTok (un concept en 35-60 s)

```bash
KIT="$(cd -P "${CLAUDE_SKILL_DIR}/../../.." && pwd)"; source "$KIT/.venv/bin/activate"; cd "$KIT"
```

Le design et l'animation viennent de **MiniMax H3** (clips motion design 2D, prompts `prompts/*.txt`). promokit ajoute ce qui doit être exact : titres, pastilles, cartes de code, sous-titres, carte de fin. Argent : règles du skill `promokit` (dry run, `BUDGET OK: $x`, cache). Programme de la série : `$KIT/100-concepts-backend-tiktok.md`. Template : `$KIT/templates/learning-tiktok/` (`promokit concept`).

## 0. Pourquoi les premiers montages étaient laids (et la règle qui corrige)

| Vu sur les planches | Cause | Règle |
|---|---|---|
| Cartes blanches avec 6-8 lignes de texte en 24 px, illisibles sur téléphone | slide « paragraphe » | 2 à 5 mots par pastille, 3 pastilles par beat, corps ≥ 40 px, titre ≥ 96 px. Un paragraphe = un fichier `display`, pas un visuel |
| Néon H3 + slide blanche + pastille grise dans la même vidéo | trois styles | un système visuel par série : mêmes couleurs dans `overlays.colors` et dans les prompts H3 (fond charbon, un accent, vert = ok, rouge = problème, ambre = étape) |
| Lignes grises « pseudo-texte » et faux boutons dans les clips | H3 invente des interfaces | prompt : « no letters, no numbers, no document-like text lines, no logos » ; le texte réel est ajouté par promokit |
| 10 s sur le même fond avec un titre | plan figé | un changement visuel toutes les 2-4 s : clip H3 (6 s, `fixed`) → fond + pastilles qui arrivent sur les mots → carte de code |
| Sous-titres sur les pastilles, texte sous les icônes TikTok | zones ignorées | titres y 240-330, pastilles y 520-900, code y 620-1100, sous-titres y 1450 ; rien à droite (x > 940) sous y 900 |
| Le titre répète la phrase dite | doublon | le titre nomme le concept (2-4 mots), la voix raconte, les pastilles prouvent |
| Carte de fin coupée, silence avant la fin | beat trop court | `extra: 1.5` sur le dernier beat, `beat_tail: 0.35` |

Test de lisibilité : `ffmpeg -i build/x.mp4 -vf "fps=1/2.5,scale=270:-1,tile=6x6" -frames:v 1 sheet_phone.png`. Ce qui n'est pas lisible à 270 px de large ne l'est pas sur TikTok.

## 1. Structure : 6 beats, 40-55 s, ~2 $

| Beat | Rôle de la voix | Durée | Visuel | Habillage |
|---|---|---|---|---|
| `hook` | situation vécue ou symptôme, ≤ 3 s pour la première phrase | 5-8 s | clip A : une personne, une réaction (documentaire) | titre 2 lignes + pastille « Concept n/100 » sur la pause |
| `def` | définition en une phrase | 6-9 s | clip B : motion design, **ancre de style** (T2VA) puis fond | `t_def` + 2 pastilles |
| `problem` | conséquence concrète | 6-9 s | clip C : même style, dominante rouge (Ref2VA) | `t_problem` + 2 pastilles |
| `how` | mécanisme en 3 temps (« un… deux… trois… ») | 8-12 s | fond + carte `code` (requête, SQL, config) | 3 pastilles numérotées calées sur `@un`, `@deux`, `@trois` |
| `prod` | la bonne pratique, un réglage, un outil | 6-9 s | clip D : même style, dominante verte (Ref2VA) | `t_prod` + 2 pastilles |
| `recap` | « À retenir : … Concept n sur cent, on continue demain. » | 6-8 s | `endcard` | `url_tag` |

Variantes : concept « comparatif » (REST vs GraphQL) → beats `a`, `b`, `critere` avec un clip `versus` ; concept « chiffres » (codes HTTP) → clip `numbers` (les chiffres sont fiables dans H3, pas les mots). Coût : voix ~0,06 $ + 4 clips 768P (0,48 $) ≈ 2 $ ; `variants/gratuit.yaml` (fond + pastilles + musique) = 0 $ et sert de validation du rythme avant de payer.

## 2. Accroche

`promokit hooks --concept "les index" --slot symptome="ta requête met 8 s"` imprime 13 familles (erreur, vécu, symptôme, mythe, enjeu, duel, chiffre, incident, entretien, interdit, avant/après, secret, express) avec un exemple validé chacune. Générer 5 candidats, garder celui dont l'image est **filmable** dans le clip A (une personne, un geste, une réaction) : la première phrase ≤ 40 caractères, concrète, qui ouvre une boucle. Le titre à l'écran = le nom du concept, jamais la phrase.

## 3. Script

- Une idée par segment, 60-120 caractères, verbe d'action, pas d'énumération de plus de trois éléments à la voix (les pastilles portent la liste).
- Débit réel mesuré : 11,3 caractères/s ; sigles et chiffres sont épelés donc plus lents. `text` = prononcé (« N plus un », « quatre cent quatre » si la voix se trompe), `display` = affiché (« N+1 », « 404 ») ; `display` est gratuit, `text` régénère la voix (0,01 $ le segment : tester `promokit vo --yes --only s1_hook` avant tout).
- Sigles et marques dans `captions.keep` pour ne jamais les couper entre deux sous-titres.
- `promokit script <projet>` : durées estimées et réelles, accroche trop longue, chiffres sans `display`, mots de remplissage, récap manquant, coût. Corriger tous les WARN avant `promokit vo`.

## 4. Direction artistique (un système par série, pas par vidéo)

- **Palette** : fond charbon `#0D1117 → #161B22`, texte `#E6EDF3`, un accent de série (`#58A6FF`), sémantique fixe : vert `#3FB950` = bon, rouge `#F85149` = problème, ambre `#D29922` = étape/attention. Les mêmes mots (« deep charcoal-navy background, soft blue glow, green and red accent pills ») dans tous les prompts H3.
- **Typographie** : Sora pour titres et pastilles, JetBrains Mono pour le code (`overlays.fonts.mono`, détecté automatiquement sinon). Tailles minimales : titre 96-110, pastille 40-44, code 34-38, sous-titres 62-76, tagline 34. Majuscules seulement sur les titres.
- **Hiérarchie** : 1 titre (nomme) → ≤ 3 pastilles (prouvent, arrivent une par une sur les mots) → sous-titres (la voix). Jamais plus de 12 mots à l'écran en même temps.
- **Pastille verre fumé** (`bg: "#161B22F0"`, `border: "#30363D"`, `dot` de couleur sémantique) : lisible sur un clip comme sur le fond ; ancre YAML `&chip_glass` puis `<<: *chip_glass`.
- **Carte de code** : `type: code`, ≤ 5 lignes, `hl` sur la ligne qui compte, `lang` juste (http, sql, python, bash = terminal). Un exemple réel et court vaut mieux qu'une liste.
- **Fond** : `type: background` avec 2 blobs de la couleur sémantique du beat (alpha 16-22, blur 100) ; `zoom 1.06-1.10` + `zoom_y` différent par beat pour que le fond vive.
- **Mouvement** : `slide: 22` sur les pastilles, `fade` 0.3-0.4 par défaut ; titre à `from: 0.0`, pastilles sur `@mot`.
- Interdits : carte blanche pleine largeur avec du texte, capture d'une doc, emoji, plus de 2 polices, texte sous y 1500 hors sous-titres, pastille de plus de 5 mots.

## 5. Clips H3 en motion design 2D (le design vient de MiniMax)

Format officiel et contrôle : skill `h3-prompting`. Bibliothèque de prompts prêts, un par famille de concept, dans [prompts/](prompts/) : `md_flow` (client ↔ serveur), `md_secure` (chiffrement, tunnel), `md_database` (table, index, requête lente), `md_cache` (raccourci, expiration), `md_queue` (file, producteur/consommateur), `md_versus` (comparatif A/B), `md_error` (panne, rouge), `md_success` (résolution, vert), `md_architecture` (blocs, monolithe → services), `md_numbers` (chiffres géants type 200/404/500), `md_person_hook` (accroche documentaire). Copier, adapter la chorégraphie au concept, garder le bloc de style.

- **Ancre de style** : le premier clip motion design (B) est en T2VA avec le bloc de style. Les suivants (C, D…) sont en Ref2VA avec `refs: [{role: reference_image, frame: {clip: B_concept, t: 2.0}}]` et `<Subject 1> is the motion design system in <Picture 1>: …` (`retention_analysis: fully_preserved`). C'est ce qui donne une série cohérente ([prompts/ref2va_style.txt](prompts/ref2va_style.txt)).
- Bloc de style validé : `Clean 2D motion design, editorial explainer style, vertical smartphone framing, deep charcoal-navy gradient background with a soft blue glow, off-white rounded modules, solid blue connector lines, green and red accent pills, icon-like squares, circles and bars only, crisp vector edges, soft grain, smooth easing, strictly abstract infographics with no letters, no numbers, no document-like text lines and no logos.`
- Deux plans, coupe `At 00:03.500`, le second plan « cuts slightly closer » ; sujet dans les 60 % centraux (titre en haut, sous-titres en bas) ; `overall_soundscape` = whooshes, ticks, pulses, « No voices, no room tone, no music » ; `non_diegetic_music: N/A`.
- Chiffres : fiables et lisibles (« 200 », « 404 », « 500 » en néon ont marché) ; lettres et mots : non fiables, ne pas en demander. Pas de logos de produits (Redis, Docker…) : une forme + la pastille promokit qui le nomme.
- Durée 6 s, 9:16, 768P ; `fixed: true` dans le beat (vitesse réelle), le fond `still` remplit le reste.
- Option I2VA : `refs: [{role: first_frame, overlay: hook_title}]` anime une image promokit (carte, diagramme) dans son propre design ; vérifier la planche, le texte peut se déformer après 2 s.
- Refaire un clip (nouveau prompt = nouveau paiement) seulement si : pseudo-texte ou logo, aplat blanc plein cadre, composition hors zone centrale, style qui ne raccorde pas avec l'ancre.

## 6. Calage sur la voix

1. `promokit vo <projet> --yes` (centimes), puis `promokit words <projet>` : début de chaque mot et pauses, avec la valeur `from` directement utilisable.
2. Dans les beats : `{id: chip_def1, from: "@certificat", to: -0.2, slide: 22}` ; `@mot:2` (2e occurrence), `@mot.end`, `@mot+0.3`. La pastille apparaît quand le mot est dit, jamais avant.
3. `promokit assemble` puis planche ; ajuster `beat_lead`/`extra` si la voix colle aux coupes.

## 7. Ordre de travail

```bash
promokit concept jour12 --num 12                    # ou --title "Index de base de données" --angle "Pourquoi ta requête prend 8 s"
promokit hooks --concept "les index"                # choisir l'accroche, écrire script + display + pastilles + prompts
promokit script jour12                              # 0 WARN
promokit overlays jour12 --variant gratuit && promokit assemble jour12 --variant gratuit --proxies   # rythme validé à 0 $
promokit plan jour12                                # ~2 $ → attendre BUDGET OK
promokit vo jour12 --yes && promokit words jour12   # caler les @mot
promokit clips jour12 --yes --only A_hook           # planche, puis B_concept (ancre), puis C_problem, D_solution
promokit assemble jour12 --sub --proxies && bash .claude/skills/promo-edit/scripts/qc.sh projects/jour12/build/jour12.mp4
```

## 8. QC avant livraison

Planche téléphone (270 px) : chaque texte lisible, aucune pastille sur un sous-titre, aucun clip avec pseudo-texte ou logo, style constant entre B, C et D, une seule idée par écran, la carte de fin visible ≥ 1,5 s après la dernière phrase. Loudness -16 LUFS, AAC 48 kHz (`qc.sh`). Livrer master, 720p, 480p et `subtitles.srt`, plus le texte du commentaire épinglé (code ou lien).
