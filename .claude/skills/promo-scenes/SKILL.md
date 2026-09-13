---
name: promo-scenes
description: "Reconnaître un site web et écrire les scènes Playwright (mini-langage promokit) qui enregistrent l'interface réelle à 30 fps avec curseur simulé, plus les captures haute résolution. Utiliser pour la section screens de project.yaml, pour sonder un site (sélecteurs, couleurs, fonts) ou corriger une scène qui échoue."
---

# Scènes produit (Playwright)

## 1. Reconnaissance (gratuit)

```bash
KIT="$(cd -P "${CLAUDE_SKILL_DIR}/../../.." && pwd)"; source "$KIT/.venv/bin/activate"
python ${CLAUDE_SKILL_DIR}/scripts/probe_site.py <url> [/page1 /page2 ...] --out /tmp/probe [--mobile]
```
Le script accepte les cookies, capture chaque page (plein écran 1920 px), liste texte, liens, boutons, champs (`id`, `placeholder`), inputs spéciaux (file, color, switch, combobox) et la palette (`--primary`, boutons, fonts). Lire les PNG avec Read. Noter ce qui exige une connexion (essayer les actions clés : import, export, IA) : ces actions seront jouées avec `fxclick` + `type`, jamais montrées avec un message d'erreur.

## 2. Écrire les scènes dans `project.yaml`

```yaml
screens:
  scenes:
    sc1_home:                                   # une scène = un mp4 + un .marks.json
      start: {url: "/", cursor: [1180, 660]}    # sans start.url : continue sur la page précédente
      steps:
        - wait: 1.2
        - mark: scroll_stats                    # repère temporel pour la timeline
        - scroll: {to: 560, dur: 1.7}
        - hover: {selector: 'a[href="/pricing"]', dur: 0.9, dy: -40}
        - click: {selector: 'button:has-text("Créatifs")', dur: 0.8, pause: 1.0}
        - click: {role: button, name: "Choisir un fichier"}
        - fxclick: {role: button, name: "Exporter PDF", pause: 1.2}   # clic visuel seulement
        - type: {selector: "#name", text: "Landry Simo", delay: 13}    # frappe réelle (React OK)
        - set_value: {selector: "input[type=color]", value: "#7c3aed"} # setter natif + events
        - click: {role: option, name: Poppins}
        - hover: {text: "Pack de 10", exact: true, dy: 140}
        - fxclick: {text: "Se connecter pour acheter", nth: 1}
        - press: Escape
        - wait_load: networkidle
  captures:                                     # image fixe haute résolution (DPR 2) d'un élément
    - id: doc
      url: "/edit?template=modern"
      dpr: 2
      out: cv_preview_2x.png
      hide_css: "header{visibility:hidden!important}"
      steps: [{fill: {selector: "#name", text: "Landry Simo"}}]
      element: {selector: "#preview"}           # ou finder_js: "() => ({x, y, width, height})" quand l'élément n'a pas de sélecteur stable
```

Mobile (TikTok/Reels) : ajouter sous `screens:` `viewport: {width: 432, height: 768, dpr: 2.5, mobile: true, cursor: tap}` ; le site est rendu en mise en page mobile réelle et filmé en 1080x1920. Avant d'écrire les scènes, sonder la page à cette taille (`probe_site.py --mobile`) : les éléments hors écran (onglets qui débordent à droite) ne sont pas cliquables, choisir ceux visibles ou `scroll_to` d'abord. Autre étape utile : `scroll_to: {selector|role|text, offset, dur}`.

Sélecteurs : `selector` (CSS Playwright, `>>` pour chaîner, `xpath=..` pour remonter), `role`+`name`, ou `text`+`exact`, avec `nth`. `dx/dy` décalent le curseur par rapport au centre de l'élément (survoler la carte au-dessus d'un bouton, par exemple).

## 3. Enregistrer et contrôler

```bash
promokit screens <projet> --only sc1_home        # puis lire screens/out/sc1_home.mp4.marks.json
ffmpeg -y -hide_banner -loglevel error -i screens/out/sc1_home.mp4 -vf "fps=1/2,scale=480:-1,tile=5x2" -frames:v 1 /tmp/sc1.png
```
Les marks donnent les instants exacts des actions : ils servent à choisir `in`/`out`/`speed` dans la timeline (skill `promo-edit`).

## App mobile sans site filmable

- Fiche Play Store : rendre la page (`hl=fr&gl=CM`), lire `document.body.innerText` (description complète, nouveautés, téléchargements) et les `img[alt*="Capture"]` ; télécharger chaque capture avec le suffixe `=s0` et l'icône avec `=s512`. Le JSON-LD donne nom, catégorie, développeur.
- Landing de l'app : sonder avec `probe_site.py`. Si le site ne répond pas depuis cette machine (vu avec GitHub Pages), cloner son dépôt : textes (`src/components`), thème (couleurs, police), captures et icône en haute résolution y sont.
- Données personnelles : les captures réelles contiennent des noms et numéros de tiers. Toujours flouter avant usage : `python ${CLAUDE_SKILL_DIR}/scripts/redact_screens.py IN OUT --top <y sous les en-têtes> --debug`, contrôle visuel, puis sans `--debug`, y compris dans les images utilisées comme référence H3.
- Positions de tap : relever les coordonnées en pixels de la capture (planche avec cercles de contrôle), puis `type: tap` avec `at: {frame: phone, image: [w, h], x, y, fit: width, pan: 0}`.

## Pièges connus et remèdes

- Bannière cookies : acceptée automatiquement au démarrage (`Tout accepter` / `Accept`). Sinon ajouter un `click` en `pre:`.
- En-tête sticky qui recouvre une capture d'élément : `hide_css: "header{visibility:hidden!important}"`.
- Input `type=file` : un vrai `click` ouvre un sélecteur système inerte (aucun upload) ; pour simuler l'import, enchaîner des `type` rapides sur les champs.
- Champs contrôlés React : `type` (frappe) ou `set_value` ; jamais `element.value=` seul.
- Bouton derrière une connexion : `fxclick` (curseur + halo, aucun événement) pour éviter le toast d'erreur.
- Une scène qui doit continuer l'état précédent (éditeur → personnalisation → export) : pas de `start.url`.
- Navigation lente (analytics ou animations qui empêchent le « network idle ») : gérée automatiquement dans les scènes et dans `probe_site.py` (DOM prêt puis 8 s max d'attente réseau, avec nouvelles tentatives).
- Une étape `type` porte un `text` à taper : utiliser `selector` pour la cible (le sélecteur est prioritaire sur `text`).
- Bouton icône sans texte (mobile) : cibler l'icône, ex. `button:has(svg.lucide-download)`.
- Sélecteur introuvable : relancer `probe_site.py` sur la page, vérifier `role`/`name` exacts (accents compris).
