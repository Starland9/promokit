# promokit

Pipeline réutilisable pour produire une vidéo de présentation d'un produit ou d'un site :
clips cinématiques **MiniMax H3**, voix off avec **votre voix clonée**, **captures réelles** de l'interface
(Playwright), habillage graphique, montage ffmpeg. Le tout **sous contrôle budgétaire strict**.

<p align="center">
  <a href="docs/media/faismoncv_promo_480p.mp4">
    <img src="docs/media/faismoncv_preview.gif" alt="Aperçu de la vidéo de présentation de Fais Mon CV produite avec promokit" width="720">
  </a>
</p>
<p align="center">
  <em>Vidéo de présentation de <a href="https://cv.starland9.dev">Fais Mon CV</a>, produite de bout en bout avec promokit (clips MiniMax H3, voix clonée, captures réelles du site).</em><br>
  <a href="docs/media/faismoncv_promo_480p.mp4"><strong>▶ Voir la vidéo complète avec le son (85 s)</strong></a>
</p>

## Les trois garde-fous anti-dépense

| Garde-fou | Comportement |
|---|---|
| **Dry run par défaut** | `promokit run`, `vo`, `clips`, `upscale` n'appellent jamais l'API payante sans `--yes`. Ils affichent d'abord le plan de coûts. |
| **Plafonds** | `budget.max_usd` (cumul du projet, lu dans le ledger) et `budget.per_call_max_usd` (un seul appel). Dépassement = refus **avant** l'appel. `max_clips_per_run` évite les boucles. |
| **Cache par contenu** | Chaque requête payante (texte + voix, prompt + images + durée + résolution) est hachée. Même requête = fichier réutilisé, 0 $. Le cache est partagé entre projets. |

Chaque appel payant est écrit dans `ledger.jsonl` **avant** d'être envoyé (statut `pending`) puis mis à jour (`done`/`failed`) :
un crash ne peut pas cacher une dépense. `promokit ledger` affiche l'historique.

Tarifs utilisés (pay-as-you-go MiniMax, relevés le 13/09/2026, modifiables sous `pricing:` dans `project.yaml`) :
H3 768P 0,08 $/s · H3 2K 0,13 $/s · régénération 768P→2K 0,05 $/s · H3-Max 480P 0,05 $/s · images de référence gratuites jusqu'à 5 puis 0,04 $ ·
TTS speech-2.8-hd 0,10 $/1 000 caractères (turbo 0,06 $) · clonage de voix 1,5 $ (jamais fait automatiquement).

Ordre de grandeur : une vidéo comme Fais Mon CV (8 segments de voix, 5 clips de 6-8 s en 768P puis 2K) = **~4,40 $**.
Stratégie économique : générer les brouillons en 768P, ne passer en 2K (`approve: true` + `promokit upscale`) que les clips validés
(768P + régénération = même prix qu'un 2K direct, mais on ne paie le 2K que pour les bons clips).

## Installation

```bash
cd promokit
uv venv .venv && source .venv/bin/activate
uv pip install -e . "playwright==1.62.0" fonttools
playwright install chromium
cp .env.example .env                           # MINIMAX_API_KEY, MINIMAX_BASE_URL, PROMOKIT_VOICE_ID
bash scripts/fetch_h3_guides.sh                # guides de prompt officiels MiniMax H3 (non redistribués ici)
promokit check faismoncv-tiktok
```

## Commandes

```bash
promokit init monprojet --url https://monsite.com   # crée projects/monprojet depuis le template commenté
promokit voices                 # voix clonées disponibles (gratuit)
promokit plan monprojet         # plan de coûts détaillé : ce qui est en cache, ce qui serait payé (gratuit)
promokit vo monprojet --yes     # voix off                       [payant, caché]
promokit clips monprojet --yes  # clips H3 brouillon 768P        [payant, caché]  --only A_hook
promokit screens monprojet      # scènes Playwright              [gratuit]        --only sc1_home
promokit overlays monprojet     # habillage Pillow               [gratuit]
promokit upscale monprojet --yes# régénération 2K des approve:true [payant, caché]
promokit assemble monprojet --sub --proxies   # montage + version sous-titrée + 720p/480p  [gratuit]
promokit run monprojet --yes --sub --proxies  # tout enchaîner (s'arrête avant de dépasser le plafond)
promokit ledger [monprojet]     # historique des dépenses
promokit cache-import monprojet # enregistrer des fichiers déjà générés (vo/, clips/) pour ne jamais les repayer
```

## Anatomie d'un projet

`projects/` est votre espace de travail : `promokit init` y crée les projets, et le dossier entier est ignoré par git. `examples/` contient l'exemple versionné.

```
project.yaml      tout le projet : site, budget, voix + script, clips + prompts, scènes, habillage, timeline
prompts/*.txt     prompts H3 (format officiel h3-prompt-writing, voir docs/h3-prompting/)
assets/           fonts, logo, musique libre de droits
vo/               voix off générées (<id>.mp3 + timings)
clips/            <id>_768P.mp4 (+ .json avec task_id), <id>_2K.mp4, images de référence extraites
screens/out/      scènes enregistrées (<nom>.mp4 + <nom>.mp4.marks.json avec les timestamps des actions), captures fixes
overlays/         PNG d'habillage
build/            vidéo finale, subtitles.srt, proxies
```

Le fichier `project.yaml` du template (16:9, timeline en segments) est commenté ligne par ligne.
[`examples/faismoncv-tiktok`](examples/faismoncv-tiktok/project.yaml) est un exemple minimal et complet au format TikTok : 3 phrases de voix off,
1 clip H3, 2 scènes du vrai site en émulation mobile, habillage, sous-titres mot à mot. Coût : ~0,49 $ si l'on génère tout
(`promokit plan faismoncv-tiktok`) ; `screens`, `overlays` et `assemble` sont gratuits. Les commandes acceptent un nom de `projects/` ou d'`examples/`, ou un chemin.

## Workflow conseillé (et économique)

1. `init`, remplir `site.url`, le `script` (une phrase par segment) et les clips avec leurs prompts.
2. `promokit plan` : vérifier le coût estimé.
3. `promokit vo --yes` (centimes) puis `promokit clips --yes --only A_hook` : valider le premier brouillon avant de lancer les autres
   (un clip dépendant d'un autre par `refs: [{frame: ...}]` attend automatiquement que le premier existe).
4. `promokit screens` : enregistrer les scènes ; lire les `*.marks.json` pour caler la timeline (`in`/`out`/`speed`).
5. `promokit overlays` puis `promokit assemble` : itérer sur la timeline autant de fois que nécessaire, c'est gratuit.
6. Quand le montage est validé : `approve: true` sur les clips gardés, `promokit upscale --yes`, `promokit assemble --sub --proxies`.

## Scènes : mini-langage (extrait)

```yaml
screens:
  scenes:
    sc1_home:
      start: {url: "/", cursor: [1180, 660]}
      steps:
        - wait: 1.2
        - mark: scroll                         # timestamp enregistré dans <scene>.mp4.marks.json
        - scroll: {to: 600, dur: 1.6}
        - hover: {selector: 'a[href="/pricing"]', dy: -40}
        - click: {role: button, name: "Commencer", dur: 0.9, pause: 0.3}
        - fxclick: {role: button, name: "Exporter PDF"}   # clic visuel seulement (bouton qui exige une connexion)
        - type: {selector: "#name", text: "Landry Simo", delay: 13}
        - set_value: {selector: "input[type=color]", value: "#7c3aed"}   # compatible React
        - scroll_to: {selector: "#linkedin", offset: 300, dur: 0.6}      # amène un élément à 300 px du haut
        - wait_load: networkidle
```

Les scènes sans `start.url` continuent sur la page précédente (utile pour enchaîner éditeur → personnalisation → export).
`captures:` produit des images haute résolution (DPR 2) d'un élément, par exemple l'aperçu d'un document.

## Timeline

`src` accepte `clip:<id>` (meilleure résolution disponible), `scene:<nom>`, `overlay:<id>` (image fixe avec pan/zoom) ou un chemin.
Les coupes franches (`xfade: 0`) sont concaténées, les fondus (`xfade: 0.5`) uniquement entre séquences.
Les temps s'écrivent relativement aux segments : `"seg3+0.5"`, `"<id>+0.5"`, `"<id>-0.2"` (avant la fin), `"end"`.
Les sous-titres sont générés depuis le script et le placement de la voix (`build/subtitles.srt`), incrustés avec `--sub`.

## Limites connues

- Pas de génération musicale : l'API musique MiniMax est fermée aux nouveaux comptes (code 2153). Utiliser une piste libre (ex. mixkit.co).
- Les fonctionnalités d'un site qui exigent une connexion doivent être jouées (`fxclick`, `type`) ou enregistrées avec un compte de test.
- Les tâches H3 ne sont interrogeables que 7 jours : la régénération 2K par `source_task_id` doit se faire dans ce délai.

## Variantes de format (TikTok, Reels, Shorts, carré)

Un même projet peut produire plusieurs formats sans repayer : `<projet>/variants/<variante>.yaml` réutilise `vo/`, `clips/`,
`prompts/`, `assets/` et remplace `video`, `screens`, `overlays`, `captions`, `timeline`, `output`. Sorties dans `screens/out/<variante>/`,
`overlays/<variante>/`, `build/<variante>/`. Toutes les commandes acceptent `--variant` :

```bash
promokit plan monprojet --variant tiktok       # 0 $ : voix et clips déjà en cache
promokit screens monprojet --variant tiktok    # scènes en émulation mobile
promokit overlays monprojet --variant tiktok
promokit assemble monprojet --variant tiktok --proxies
```

Une variante contient seulement les clés qui changent, par exemple `video: {width: 1080, height: 1920, fps: 30}`, `screens`, `overlays`,
`captions`, `timeline` et `output` (même contenu que dans [l'exemple TikTok](examples/faismoncv-tiktok/project.yaml)). Briques utilisées :

| Brique | Clé | Effet |
|---|---|---|
| Émulation mobile | `screens.viewport: {width: 432, height: 768, dpr: 2.5, mobile: true, cursor: tap}` | vrai rendu mobile du site, 1080x1920, halo de « tap » au lieu d'une flèche |
| Téléphone | overlay `type: device_frame` + segment `frame: phone` | l'enregistrement est placé dans un téléphone sur le dégradé de marque |
| Recadrage | segment `crop_x` / `crop_y` (0 à 1) | un clip 16:9 devient 9:16 en gardant le sujet |
| Beats | `timeline.beats[]` | une phrase de voix off = un beat ; sa durée suit la voix, les plans `flex` sont accélérés ou ralentis, les plans `fixed: true` gardent leur vitesse |
| Rythme | `timeline.audio.vo_tempo: 1.08` | voix plus rapide sans changer la hauteur, sans nouvelle synthèse |
| Sous-titres TikTok | `captions: {mode: words, burn: true, max_words: 3, highlight: "#FFD84D", keep: ["Fais Mon CV"]}` | 2-3 mots à l'écran, mot actif surligné, calés sur les pauses réelles de la voix, marques jamais coupées |
| Texte affiché | `script[].display` | sous-titres avec l'orthographe réelle (« 17 », « cv.starland9.dev ») quand la voix épelle ; gratuit, n'invalide pas le cache |

Zones sûres TikTok (1080x1920) : garder le texte entre y ≈ 180 et y ≈ 1500, et loin du bord droit (icônes) sous y ≈ 900.

### Timeline en beats (extrait)

```yaml
timeline:
  beat_lead: 0.25          # la voix démarre 0,25 s après le début du beat
  beat_tail: 0.2
  audio: {vo_tempo: 1.08, music: {src: assets/music/bed.mp3, gain: 0.55}}
  beats:
    - id: hook
      vo: s1_hook
      shots:
        - {src: "clip:A_hook", in: 0.0, out: 4.4, crop_x: 0.38, fixed: true, ambient: 0.3}
        - {src: "clip:A_hook", in: 4.6, out: 7.9, crop_x: 0.65}          # flex : remplit le reste du beat (sans out = jusqu'à la fin)
      overlays:
        - {id: hook_title, from: 0.0, to: -0.3}                         # to négatif = avant la fin du beat
    - id: templates
      vo: s3_templates
      shots: [{src: "scene:m2_templates", in: 0.3, out: 10.0, frame: phone}]
      overlays: [{id: chip_templates, from: 0.1, to: -0.15, slide: 20}]
```

## Apps mobiles (Play Store, App Store)

Une app native ne se filme pas avec Playwright : on anime ses captures d'écran. Cette méthode a servi à produire la vidéo TikTok de l'app Android Omoh,
en deux versions : musique et textes à 0 $, puis voix off et 2 clips H3 pour 1,62 $.

1. **Récupérer les écrans** : captures de la fiche Play Store (`play-lh.googleusercontent.com/...=s0` = pleine résolution), icône (`=s512`), et celles de la landing si elle existe (dépôt Git de la landing si le site est injoignable).
2. **Protéger les données** : les captures réelles montrent souvent des noms et numéros de tiers. Garder les originaux dans `assets/raw/` et flouter les lignes de texte secondaire avant usage :
   `python .claude/skills/promo-scenes/scripts/redact_screens.py assets/raw/liste.jpg assets/screens/liste.png --top 1240 --debug` (retirer `--debug` une fois les zones vérifiées). Pour un défilement, assembler plusieurs captures floutées en une image haute avec Pillow.
3. **Animer** dans le téléphone (`frame: phone`) :

| Segment image | Effet |
|---|---|
| `fit: width` | la capture remplit la largeur de l'écran du téléphone |
| `pan_from: 0, pan: 1` | défilement vertical adouci (liste longue) |
| `zoom_from: 1.2, zoom: 1.0, zoom_x, zoom_y` | zoom avant ou arrière centré sur un point |
| `fit: contain, pad_color` | capture entière, bandes de la couleur de fond de l'app |

| Overlay | Usage |
|---|---|
| `type: tap` avec `at: {frame: phone, image: [1080, 2168], x, y, fit: width}` | toucher simulé, positionné en pixels de la capture |
| `type: magnify` (`src`, `box`) | loupe : zone agrandie de la capture au-dessus du téléphone |
| `type: notification` | notification SMS/app qui glisse (accroche « problème ») |
| `type: background` (`color`, `to`, `blobs`) | fond de marque ; réutilisable par `endcard.bg` et `device_frame.bg` via une ancre YAML |
| `type: endcard` avec `icon`, `name`, `accent`, `pill_bg` | carte de révélation ou de fin avec l'icône de l'app |

4. **Monter sur la musique** (version sans voix, 0 $) : `timeline.bpm` (donné par `beatgrid.py`), `beats[].bars`, et durées musicales partout (`from: 2b`, `to: 1bar`, `len: 1bar`, `to: -0.05`). Sans `script`, l'assemblage fait un mix musique seule normalisé.

```bash
python .claude/skills/promo-edit/scripts/beatgrid.py projects/monapp/assets/music/track.mp3   # bpm, mesures, music.in conseillé
promokit plan monapp --variant gratuit          # 0 $ si la variante a script: [] et clips: []
promokit overlays monapp --variant gratuit && promokit assemble monapp --variant gratuit --proxies
```

## Ce qui n'est pas dans le dépôt

| Exclu | Pourquoi | Comment le retrouver |
|---|---|---|
| `.env`, `ledger.jsonl`, `cache/` | secrets, dépenses, médias payés | `.env.example` ; le cache se reconstruit à l'usage |
| `projects/` (entier) | votre espace de travail : projets, marques, captures, médias | `promokit init` |
| `examples/*/vo`, `clips`, `screens/out`, `overlays`, `build`, `assets/music` | médias générés ou sous licence | `promokit vo/clips` (payant), `screens/overlays/assemble` (gratuit), piste libre à télécharger |
| guides H3 (`base-en.txt`, `ref-en.txt`) | MiniMax H3 Community License | `bash scripts/fetch_h3_guides.sh` |

Sans musique, l'assemblage continue et le signale. Les polices du template sont sous SIL Open Font License (`OFL-*.txt`) ;
`scripts/fetch_fonts.sh` les retélécharge.

## Agent et skills Claude Code

`.claude/` contient un sous-agent et quatre skills. Claude Code les découvre en ouvrant ce dossier. Pour les utiliser depuis un dossier parent, créer des liens symboliques dans son `.claude/` ; les skills retrouvent le kit à travers les liens.

| Élément | Rôle |
|---|---|
| agent `promo-producer` | Produit une vidéo de bout en bout (reconnaissance, script, prompts, scènes, montage, QC). N'ajoute `--yes` que si le message contient `BUDGET OK: $<montant>` et que `promokit plan` est en dessous. Invocation : « Utilise le sous-agent promo-producer pour … » ou `@agent-promo-producer`. |
| `/promokit` | Orchestration et règles d'argent, commandes, planches de contrôle. |
| `/h3-prompting` | Écriture des prompts H3 (guides officiels via `scripts/fetch_h3_guides.sh`, exemples validés, cohérence de personnage). |
| `/promo-scenes` | Reconnaissance d'un site (`scripts/probe_site.py`), mini-langage des scènes Playwright, floutage de captures (`scripts/redact_screens.py`). |
| `/promo-edit` | Script de voix off, timeline, habillage, audio, montage sur la musique (`scripts/beatgrid.py`), QC (`scripts/qc.sh`). |

Exemple : `Utilise le sous-agent promo-producer pour une vidéo de présentation de https://monsite.com. BUDGET OK: $5`.
Sans la phrase de budget, l'agent livre une version à 0 $ et le plan de coûts de la version complète, sans rien dépenser.
