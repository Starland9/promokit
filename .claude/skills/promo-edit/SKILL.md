---
name: promo-edit
description: "Écrire le script de voix off, le storyboard et la timeline promokit (segments, coupes, fondus, habillage, audio) puis contrôler la qualité du montage (planche de contrôle, loudness, sous-titres). Utiliser pour les sections script, overlays et timeline de project.yaml, et avant toute livraison de vidéo."
---

# Script, timeline et QC

## 1. Script de voix off (`script:`)

- Quatre lignes de colonne vertébrale avant d'écrire : un spectateur, une promesse, un mécanisme (3 étapes max), une prochaine action (l'URL).
- Registre simple, tutoiement si la marque tutoie, phrases courtes, aucun chiffre invérifiable. La voix porte l'argument, l'écran porte la preuve : ne pas décrire ce qu'on voit, ne pas montrer ce qu'on dit.
- 6 à 8 segments, 60–70 s de voix au total (≈ 15 caractères/seconde avec `speech-2.8-hd`). Segment le plus long ≤ 16 s.
- Texte prononcé ≠ texte affiché : `text:` est ce que dit la voix (URL et nombres épelés : « CV point starland neuf point dev », « dix-sept »), `display:` est ce qu'affichent les sous-titres (« cv.starland9.dev », « 17 »). Modifier `display` est gratuit (la clé de cache de la voix ne dépend que de `text`).
- Enchaînement type : accroche (problème vécu) → promesse → étape 1 → étape 2 → étape 3 → preuve/résultat → prix/accès → appel à l'action + nom de marque.
- Coût : 0,10 $ / 1 000 caractères ; un script complet ≈ 0,08 $. Changer un mot = régénérer ce segment seulement.

## 2. Storyboard → timeline

Alterner clips H3 (émotion, contexte) et scènes écran (preuve). Un visuel par idée ; couper sur une fin de phrase ; jamais plus de 4 s sur une image fixe générée.

```yaml
timeline:
  segments:
    - {id: hook, src: "clip:A_hook", in: 0.0, out: 8.0, xfade: 0.5}        # fondu vers le suivant
    - {id: home, src: "scene:sc1_home", in: 0.3, out: 8.5, speed: 1.6, xfade: 0}   # coupe franche (concat)
    - {id: home2, src: "scene:sc1_home", in: 8.5, out: 12.2, xfade: 0}
    - {id: doc, src: "overlay:pdf_hero", still: true, len: 3.4, pan: 0.55, zoom: 1.05, xfade: 0.6}
    - {id: end, src: "overlay:endcard", still: true, len: 5.0, zoom: 1.03}
  overlays:
    - {id: hook_title, t: ["hook+1.0", "hook-0.6"], fade: 0.5, slide: 24}
    - {id: url_tag, t: ["home+0.3", "end-5.0"], fade: 0.5}
  audio:
    vo: [{id: s1_hook, t: "hook+0.7"}, {id: s2_intro, t: "home+0.4"}]
    ambient: [{src: "clip:A_hook", in: 0, out: 8, t: "hook+0", gain: 0.35}]
    music: {src: assets/music/bed.wav, gain: 0.5, sc_thresh: 0.02, sc_ratio: 6}
```

- `in`/`out` viennent des `screens/out/<scène>.mp4.marks.json` : commencer juste avant un mark, finir juste après l'action.
- Vitesses : frappe clavier 1.5×, défilement 1.3–1.6×, transitions de page 2–3×, clic important 1.0×. Une scène de 20 s se ramène à ~12 s sans perdre les gestes.
- Fondu (`xfade` 0.5–0.8) seulement entre sources différentes (clip ↔ écran ↔ image fixe). Entre deux morceaux de la même scène : `xfade: 0`.
- Voix : chaque segment commence 0,2–0,7 s après le début de son visuel ; vérifier qu'un segment finit avant le suivant (durées dans `vo/*.mp3` via `ffprobe`), sinon décaler.
- Habillage : pastilles en bas à gauche, une par bénéfice, 5–8 s chacune ; URL en bas à droite du premier écran produit jusqu'à l'end card ; titre d'accroche sur le premier clip uniquement.
- Audio : ambiance des clips à 0,25–0,35, musique 0,5 avec ducking (sidechain) sous la voix, normalisation finale -16 LUFS, AAC 48 kHz (des lecteurs ne décodent pas 96 kHz).

## 2 bis. Format vertical (TikTok, Reels, Shorts)

Variante `variants/<format>.yaml` (ou projet vertical direct). Exemple complet et minimal : `examples/faismoncv-tiktok/project.yaml`.

- **Beats** plutôt que segments : `timeline.beats[]`, un beat par segment de voix off (`vo:`), `beat_lead`/`beat_tail`. Les plans `fixed: true` (clips H3) gardent leur vitesse, les plans flex (scènes écran, images fixes sans `fixed`) sont ajustés pour remplir la durée ; le journal d'assemblage signale une vitesse hors 0,5–4.
- **Accroche** dans la première seconde : titre en haut (`type: title`, `caps: true`, `gradient: top`, y ≈ 250) sur un plan émotionnel ; première voix à `lead: 0.15`.
- **Rythme** : `audio.vo_tempo: 1.08` (gratuit, pas de nouvelle synthèse), coupes franches, fondus 0,3 s seulement à l'entrée ou la sortie du téléphone. Viser 45–65 s.
- **Clips 16:9 → 9:16** : un plan par prise de vue du clip, `crop_x` calé sur le sujet (vérifier avec une planche : `scale=-2:1440,crop=810:1440:x='(iw-ow)*CX'`). Deux personnes éloignées ne tiennent pas dans le cadre : choisir celle qui porte le message.
- **Interface** : overlay `type: device_frame` (x 180, y 370, w 720, h 1280) et `frame: phone` sur chaque scène mobile.
- **Pastilles** : `type: chip`, `align: center`, `y: 200`, `size: 40`, textes de 2 à 5 mots.
- **Sous-titres** : `captions: {mode: words, burn: true, max_words: 3, max_chars: 18, min_duration: 0.45, caps: true, highlight: "#FFD84D", y: 1700, font_file: assets/fonts/Sora.ttf, weight: 800, keep: ["Fais Mon CV", "1 000"]}`. Le mot actif est calé sur les pauses détectées dans la voix ; `keep` empêche de couper une marque ou un montant entre deux sous-titres ; les sous-titres trop courts sont fusionnés.
- **Zones sûres** : texte entre y ≈ 180 et y ≈ 1500 (sous-titres jusqu'à y ≈ 1700) ; rien d'important à droite (x > 940) sous y ≈ 900 ; end card `y: 470` pour laisser la place aux sous-titres.
- **Calage sur les mots** : après `promokit vo`, `promokit words <projet>` donne le début de chaque mot ; dans un beat, `from: "@certificat"` (aussi `@mot:2`, `@mot.end`, `@mot+0.3`) fait apparaître la pastille quand le mot est dit. Plus fiable que de lire les pauses à la main.
- **Code à l'écran** : overlay `type: code` (`lang: http|sql|python|bash|json|yaml`, `lines`, `hl: [n]`, `title`, `size: 36-40`, ≤ 5 lignes, police mono détectée automatiquement) ; jamais une capture de doc ni une carte blanche pleine de texte.
- **Lisibilité** : planche à l'échelle téléphone `scale=270:-1` ; ce qui n'y est pas lisible ne l'est pas sur TikTok. Tailles minimales : titre 96, pastille 40, code 34, sous-titres 62. Vidéo pédagogique (concept expliqué) : skill `tiktok-learning`.

## 2 ter. Montage sur la musique (sans voix off, 0 $)

- `python ${CLAUDE_SKILL_DIR}/scripts/beatgrid.py <musique>` : `timeline.bpm`, mesures, et `music.in` qui fait tomber le drop sur la fin de l'accroche.
- `beats[].bars: N` (pas de `vo`) ; durées musicales partout : `len: 1bar`, `from: 2b`, `to: 1bar`, `to: -0.05` (avant la fin du beat). Couper sur les mesures, faire apparaître les éléments sur les temps (notifications, points d'une liste).
- Structure qui marche (35 s) : accroche problème 2 mesures → révélation de l'app 1 mesure (sur le drop) → 3 à 4 démonstrations de 1 à 2 mesures chacune, une pastille par bénéfice → preuve (confidentialité, prix) 2 mesures → fin 2 mesures + 1,2 s.
- Texte à l'écran = seul porteur du message : 6 mots max par pastille, titre d'accroche en majuscules avec 1–2 mots en couleur d'accent.
- Musique `gain: 0.9`, `fade_in: 0.05`, `fade_out: 1.8` ; la normalisation finale ramène à -16 LUFS.

## 3. Musique

Pas de génération (API MiniMax fermée aux nouveaux comptes). Piste libre : Mixkit (`https://assets.mixkit.co/music/<id>/<id>.mp3`, licence gratuite sans attribution), puis `ffmpeg -i x.mp3 -af loudnorm=I=-18:TP=-2:LRA=9 -ar 48000 -ac 2 assets/music/bed.wav`. Sous une voix : tempo 100–115 bpm, peu dense (underscore corporate). Sans voix (TikTok) : hip-hop 90–100 bpm à rythme marqué (ex. Mixkit « Hip Hop 03 », Lily J). Analyser plusieurs pistes avec `beatgrid.py` avant de choisir.

## 4. QC avant livraison

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/qc.sh projects/<projet>/build/<video>.mp4
```
Le script produit la planche de contrôle (`_sheet.png`, à lire avec Read), la loudness (cible I -16 LUFS, pic ≤ -1 dBTP), les flux (h264 1920x1080 30 fps, aac 48000 Hz) et signale les chevauchements de sous-titres. Vérifier sur la planche : aucune image noire, la vidéo ne saute pas à l'end card avant la fin, chaque pastille correspond à ce qui est à l'écran, aucun toast d'erreur ni bannière cookies, le curseur est visible pendant les clics.

Livraison : `assemble --sub --proxies` fournit master, version sous-titrée, 720p, 480p et `subtitles.srt`. Envoyer le 480p si le transfert est limité.
