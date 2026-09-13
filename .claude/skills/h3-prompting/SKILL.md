---
name: h3-prompting
description: "Écrire les prompts des clips vidéo MiniMax H3 (Hailuo 03) pour promokit, en mode texte (T2VA), première image (I2VA) ou références (Ref2VA) avec cohérence de personnage entre clips. Utiliser dès qu'il faut créer ou corriger un fichier prompts/*.txt ou un clip H3."
---

# Prompts MiniMax H3

Format officiel (skill `h3-prompt-writing` de MiniMax, non redistribué ici : s'il manque, lancer `bash "${CLAUDE_SKILL_DIR}/../../../scripts/fetch_h3_guides.sh"`). Lire le guide complet seulement si nécessaire : [base-en.txt](base-en.txt) (T2VA / I2VA / FL2VA / L2VA) et [ref-en.txt](ref-en.txt) (Ref2VA, six sections). Exemples validés : [example-t2va.txt](example-t2va.txt), [example-ref2va.txt](example-ref2va.txt).

## Structure minimale (T2VA, sans image de référence)

```
integrated_multimodal_description: [Shot 1] <style>, <cadrage>, <sujet précis>, <décor>, <action>, <mouvement caméra en anglais naturel>. [Shot 2] At 00:04.500, the camera cuts to <...>.

overall_soundscape: <ambiance et bruits d'action, 1–4 phrases>

non_diegetic_music: N/A
```

Avec images de référence (Ref2VA), six sections dans cet ordre : `subject_definitions` (`<Subject 1> is the man in <Picture 1>: ...`), `summary` (`[reference generation] ...`), `retention_analysis` (`<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - ...`), `detailed_description` (style d'abord, puis `[Shot 1] ...`), `overall_soundscape`, `non_diegetic_music`. Les libellés `<Picture N>` suivent l'ordre des `refs:` du clip dans `project.yaml`.

## Ce qui a marché (Fais Mon CV)

- Réalisme documentaire : « Live-action, documentary realism, natural window light, shallow depth of field, 50mm photographic feel ». Bannir « cinematic / magical / neon / glowing / floating », les logos et les HUD.
- Sujet ancré et précis : âge, tenue, lieu nommé (« a young Cameroonian man in his mid-20s, light blue short-sleeved shirt, modest bright apartment in Douala »).
- Deux plans maximum par clip de 6–8 s, coupe à `At 00:03.500` ou `At 00:04.500`.
- Aucun texte lisible à l'écran (le texte est ajouté au montage), aucune parole (la voix off est séparée), `non_diegetic_music: N/A` (musique au montage). L'ambiance dans `overall_soundscape` sert de lit sonore à faible volume.
- Cohérence de personnage : générer le clip d'ancrage d'abord, puis `refs: [{role: reference_image, frame: {clip: A_hook, t: 1.5}}]` sur les autres ; décrire dans `retention_analysis` ce qui change (tenue, lieu) en `partially_preserved`.
- Interface réelle dans un clip : passer la capture du site en `reference_image` et la définir comme `<Subject 2>` (« the website interface shown in <Picture 2>: white page, bold wordmark "…", blue button »). Fonctionne bien sur un écran de laptop en plan épaule.
- Durée entière 4–15 s ; `ratio: "16:9"` (ou `9:16` pour TikTok) ; brouillon 768P, 2K seulement après validation.

## Contrôle après génération

```bash
ffmpeg -y -hide_banner -loglevel error -i clips/<id>_768P.mp4 -vf "fps=1,scale=480:-1,tile=4x2" -frames:v 1 clips/<id>_sheet.png
```
Lire la planche. Refaire un prompt (nouveau texte = nouvelle clé de cache, donc nouveau paiement) seulement si le défaut est réel : mains/visage déformés, texte inventé, mauvais cadrage, action absente.
