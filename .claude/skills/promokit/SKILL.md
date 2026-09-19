---
name: promokit
description: "Pipeline promokit pour produire une vidéo de présentation d'un site ou d'une app (clips MiniMax H3, voix off clonée, captures Playwright, montage ffmpeg) avec plafond de dépenses, cache et ledger. Utiliser pour toute demande de vidéo promo/présentation/démo, ou quand promokit, H3, Hailuo, MiniMax, voix off sont mentionnés."
argument-hint: "[projet] [plan|run|vo|clips|screens|overlays|assemble|upscale|ledger]"
allowed-tools: Bash(promokit *), Bash(ffmpeg *), Bash(ffprobe *), Read, Glob, Grep
---

# promokit

Racine du kit (fonctionne aussi quand le skill est un lien symbolique) :

```bash
KIT="$(cd -P "${CLAUDE_SKILL_DIR}/../../.." && pwd)"; source "$KIT/.venv/bin/activate"; cd "$KIT"
```

Projets dans `$KIT/projects/<nom>/project.yaml` (espace de travail, ignoré par git). Exemple minimal versionné : `$KIT/examples/faismoncv-tiktok` (TikTok : voix off, 1 clip H3, scènes mobiles, sous-titres mot à mot). Template 16:9 commenté : `$KIT/templates/project/project.yaml`. Si `projects/` contient déjà des projets aboutis, s'en servir comme modèles. Doc détaillée : `$KIT/README.md`. Premier lancement sur une nouvelle machine : `bash $KIT/scripts/fetch_h3_guides.sh`.

Demande reçue : `$ARGUMENTS`

## Argent : les règles

| Règle | Détail |
|---|---|
| Dry run par défaut | `vo`, `clips`, `upscale`, `run` affichent le plan et s'arrêtent. `--yes` seulement avec accord explicite de l'utilisateur sur un montant (`BUDGET OK: $x`) et si `promokit plan` ≤ ce montant. |
| Plafonds | `budget.max_usd` (cumul projet, lu dans `ledger.jsonl`) et `budget.per_call_max_usd`. Ne pas les modifier sans demande explicite. |
| Cache | Même texte+voix ou même prompt+images+durée+résolution = déjà payé, réutilisé. Ne jamais utiliser `--force` sans raison. |
| Jamais | appeler l'API MiniMax directement, cloner une voix (`landry-promo` existe), lancer `clips` sur tous les clips d'un coup avant d'avoir validé le premier, passer en 2K avant que le montage soit validé. |

Tarifs (pay-as-you-go, 13/09/2026) : H3 768P 0,08 $/s · 2K 0,13 $/s · régénération 768P→2K 0,05 $/s · images de référence gratuites jusqu'à 5 · TTS HD 0,10 $/1 000 caractères. Une vidéo type (8 segments de voix, 5 clips de 6–8 s en 768P puis 2K) ≈ 4,40 $.

## Commandes

```bash
promokit check <projet>            # outils, clé API, voix clonées (gratuit)
promokit init <projet> --url <url> # nouveau projet depuis le template commenté
promokit plan <projet>             # estimation : cache vs à payer (gratuit)
promokit vo <projet> [--yes] [--only s1_hook]        # voix off
promokit clips <projet> [--yes] [--only A_hook]      # brouillons H3 768P (dépendances frame: automatiques)
promokit screens <projet> [--only sc1_home]          # scènes Playwright + captures (gratuit)
promokit overlays <projet>                           # PNG d'habillage (gratuit)
promokit assemble <projet> [--sub] [--proxies]       # montage (gratuit, itérer autant que nécessaire)
promokit upscale <projet> [--yes] [--only A_hook]    # 2K des clips approve: true
promokit run <projet> [--yes] [--sub] [--proxies]    # tout enchaîner
promokit ledger [<projet>]                           # dépenses
# toutes les commandes acceptent --variant <nom> (variants/<nom>.yaml : tiktok, reels, carré...) qui réutilise voix et clips payés
promokit cache-import <projet> [--record-spend]      # enregistrer des fichiers déjà générés
# vidéo pédagogique (skill tiktok-learning), tout gratuit :
promokit concept <projet> --num 12 | --title "…" --angle "…"   # projet depuis templates/learning-tiktok (6 beats, 4 clips H3 motion design)
promokit hooks --concept "…" [--slot symptome="…"]   # 13 familles d'accroches avec exemples
promokit script <projet>                             # lint du script : durées, accroche, display, récap, coût
promokit words <projet> [--only s1_hook]             # début de chaque mot de la voix générée -> from: "@mot" dans les beats
```

## Ordre de travail

1. Reconnaissance du site (skill `promo-scenes`, script `probe_site.py`).
2. `project.yaml` : `site.url`, `script` (skill `promo-edit`), `clips` + `prompts/*.txt` (skill `h3-prompting`), `screens`, `overlays`, `timeline`.
3. `promokit plan` → rapporter le coût. Sans accord chiffré, s'arrêter ici avec le plan et les scènes déjà enregistrées.
4. Gratuit : `screens`, `overlays`, `assemble` (les segments `clip:` manquants font échouer l'assemblage : utiliser temporairement une image fixe `overlay:` ou retirer le segment).
5. Payant autorisé : `vo --yes` → `clips --yes --only <premier>` → planche de contrôle → autres clips → `assemble` → `approve: true` → `upscale --yes` → `assemble --sub --proxies`.
6. QC (skill `promo-edit`) puis rapport avec `promokit ledger <projet>`.

## Sans budget chiffré : livrer quand même une vidéo

Sans `BUDGET OK: $x`, ne pas s'arrêter au plan : produire une version complète à 0 $ dans `variants/gratuit.yaml` (`script: []`, `clips: []`, montage sur la musique avec textes, écrans réels et habillage), la livrer, puis préparer la version payante dans `project.yaml` (script, prompts H3 en 9:16) et la valider sans dépense : copie du projet dans le scratchpad, voix et clips remplacés par des fichiers factices de durée réaliste, `assemble` sur la copie. Rapporter le coût exact de `promokit plan`. Structure : `variants/gratuit.yaml` avec `script: []`, `clips: []`, `timeline.bpm` et `beats[].bars` (README, section « Apps mobiles »).

## Vidéo pédagogique (concept expliqué, série « 100 Concepts Backend »)

Skill `tiktok-learning` : structure en 6 beats, accroches, lint du script, direction artistique lisible sur téléphone, clips H3 en motion design 2D cohérents (ancre de style + Ref2VA), calage des pastilles sur les mots (`@mot`), QC à l'échelle téléphone. `promokit concept <nom> --num <n>` crée le projet ; `--variant gratuit` donne une version à 0 $.

## App mobile (Play Store / App Store)

Pas de scène Playwright : captures de la fiche (`=s0`), icône, landing ; floutage des données de tiers (`.claude/skills/promo-scenes/scripts/redact_screens.py`) ; animation des captures dans `frame: phone` (fit, pan, zoom, `tap` avec `at`, `magnify`, `notification`). Détails : README section « Apps mobiles », skills `promo-scenes` et `promo-edit`.

## Autre format (TikTok, Reels, Shorts, carré)

Ne jamais créer un nouveau projet pour un nouveau format : créer `projects/<projet>/variants/<format>.yaml` (clés de format reprises de `examples/faismoncv-tiktok/project.yaml`), puis `plan --variant` (doit afficher 0 $ si la voix et les clips existent), `screens --variant`, `overlays --variant`, `assemble --variant --proxies`. Détails de mise en page verticale : skill `promo-edit`.

## Planche de contrôle d'un fichier

```bash
ffmpeg -y -hide_banner -loglevel error -i <fichier.mp4> -vf "fps=1/2.5,scale=384:-1,tile=6x6" -frames:v 1 sheet.png   # vidéo entière
ffmpeg -y -hide_banner -loglevel error -i <clip.mp4> -vf "fps=1,scale=480:-1,tile=4x2" -frames:v 1 clip_sheet.png    # clip H3
```
Lire le PNG avec Read avant de juger un clip ou un montage.
