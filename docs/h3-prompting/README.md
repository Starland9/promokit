Guide de prompt officiel MiniMax H3 (copié depuis https://github.com/MiniMax-AI/MiniMax-H3, skill `h3-prompt-writing`).

- `base-en.txt` : modes texte / première image / première+dernière image (champs `integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music`).
- `ref-en.txt` : mode référence complète (images/vidéos/audio de référence) en six sections (`subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`).

Règles qui ont bien marché sur le projet Fais Mon CV :
- réalisme documentaire, lumière naturelle, focale 35/50 mm, pas de « cinematic/magique/néon » ;
- pas de texte à l'écran dans les clips (le texte est ajouté au montage) ;
- `non_diegetic_music: N/A` (la musique est ajoutée au montage), ambiance décrite dans `overall_soundscape` ;
- pour garder le même personnage : extraire une image du premier clip et la passer en `reference_image` (voir `refs: [{frame: {clip: A_hook, t: 1.5}}]`).
