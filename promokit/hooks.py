"""Educational (learning) TikTok tooling: hook formulas, script lint, voice-over word timings, concept scaffolding.
Nothing here calls a paid API."""
from __future__ import annotations
import pathlib, re, shutil, subprocess, unicodedata

# ----------------------------------------------------------------------------- hooks
# Slots: {concept} {erreur} {symptome} {consequence} {idee_recue} {chiffre} {a} {b} {question} {situation} {regle} {acteur} {resultat}
HOOK_FAMILIES = [
    {"id": "erreur", "name": "L'erreur courante", "pattern": "L'erreur que presque tout le monde fait avec {concept} ? {erreur}.",
     "example": "L'erreur HTTP la plus bête ? Utiliser GET pour une action qui modifie des données.", "why": "Le spectateur se demande s'il la fait aussi (auto-vérification)."},
    {"id": "vecu", "name": "La situation vécue", "pattern": "Tu as déjà {situation} ? Voilà ce qui se passe vraiment.",
     "example": "Tu t'es déjà connecté au WiFi d'un café ? Sur un site HTTP, tout ce que tu envoies passe en clair.", "why": "Ancrage dans une scène concrète, image immédiate pour le clip d'accroche."},
    {"id": "symptome", "name": "Le symptôme mystère", "pattern": "{symptome} ? Dans 9 cas sur 10, c'est {concept}.",
     "example": "Ta requête met 8 secondes ? Dans 9 cas sur 10, il manque un index.", "why": "Part de la douleur, promet la cause : boucle ouverte jusqu'à l'explication."},
    {"id": "mythe", "name": "Le mythe démonté", "pattern": "Non, {idee_recue}. Et ça change tout.",
     "example": "Non, un JWT n'est pas chiffré. N'importe qui peut le lire.", "why": "Contredit une croyance : le spectateur reste pour vérifier."},
    {"id": "enjeu", "name": "La conséquence", "pattern": "{concept} mal géré, c'est {consequence}.",
     "example": "Un cookie de session volé, c'est ta session prise.", "why": "Rend l'abstrait dangereux et concret en une phrase."},
    {"id": "versus", "name": "Le duel", "pattern": "{a} contre {b} : le vrai critère, ce n'est pas {idee_recue}.",
     "example": "REST contre GraphQL : le vrai sujet, ce n'est pas lequel est plus moderne.", "why": "Format débat, déclenche les commentaires."},
    {"id": "chiffre", "name": "Le chiffre choc", "pattern": "{chiffre}. C'est {consequence}. La cause : {concept}.",
     "example": "1 000 requêtes SQL pour afficher 10 utilisateurs. La cause : le problème N+1.", "why": "Un nombre précis arrête le scroll ; il doit être vérifiable."},
    {"id": "incident", "name": "L'incident raconté", "pattern": "Il est {heure}, {situation}. La cause : {concept}.",
     "example": "Il est 23 h, la prod tombe sous 200 utilisateurs. La cause : 1 000 connexions ouvertes vers la base.", "why": "Mini-récit : tension, puis résolution dans la vidéo."},
    {"id": "entretien", "name": "La question d'entretien", "pattern": "Question d'entretien classique : {question}. La plupart répondent faux.",
     "example": "Question d'entretien classique : différence entre PUT et PATCH ? La plupart répondent faux.", "why": "Cible directement les juniors qui préparent des entretiens."},
    {"id": "interdit", "name": "La règle absolue", "pattern": "Ne fais jamais {erreur}. Voilà pourquoi.",
     "example": "Ne stocke jamais un mot de passe en clair. Voilà pourquoi bcrypt existe.", "why": "Injonction claire, promesse d'explication."},
    {"id": "avant_apres", "name": "Avant / après", "pattern": "Avant : {symptome}. Après {concept} : {resultat}.",
     "example": "Avant : 8 secondes par requête. Après un index : 20 millisecondes.", "why": "Transformation visible, idéale avec un clip motion design en deux temps."},
    {"id": "secret", "name": "Ce qu'on ne t'a pas dit", "pattern": "Ce que {acteur} fait avec {concept}, et que ton tuto ne t'a jamais montré.",
     "example": "Ce que Stripe fait avec les clés d'idempotence, et que ton tuto ne t'a jamais montré.", "why": "Curiosité + autorité ; exige un fait réel et sourcé."},
    {"id": "express", "name": "Le défi express", "pattern": "{concept} expliqué en {duree} secondes, sans bullshit.",
     "example": "OAuth 2 expliqué en 45 secondes, sans bullshit.", "why": "Promesse de format ; fonctionne surtout pour les concepts intimidants."},
]
HOOK_RULES = [
    "Première phrase ≤ 3 s de voix (≈ 40 caractères) et une image forte : c'est elle qui décide si le spectateur reste.",
    "Concret avant abstrait : une scène, un symptôme, un chiffre. Le nom du concept arrive après.",
    "Ouvrir une boucle (question, cause annoncée mais pas donnée) et la fermer dans la vidéo.",
    "Un seul hook par vidéo ; le titre à l'écran ne répète pas la phrase, il nomme le concept (2 à 4 mots).",
    "Aucun chiffre invérifiable, aucune promesse que la vidéo ne tient pas.",
]

def fill(pattern: str, slots: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: slots.get(m.group(1), m.group(0)), pattern)

def print_hooks(slots: dict | None = None, family: str | None = None, log=print):
    slots = slots or {}
    log("HOOKS pour une vidéo pédagogique (remplir les {slots} restants, garder ≤ 40 caractères pour la première phrase)\n")
    for h in HOOK_FAMILIES:
        if family and family not in (h["id"], h["name"].lower()): continue
        log(f"[{h['id']}] {h['name']}")
        log(f"   {fill(h['pattern'], slots)}")
        log(f"   ex. {h['example']}")
        log(f"   → {h['why']}\n")
    log("Règles :"); [log(f"  - {r}") for r in HOOK_RULES]

# ----------------------------------------------------------------------------- script lint
CPS = 11.5   # measured on 27 real MiniMax speech-2.8-hd French segments: 11.3 chars/s before vo_tempo (acronyms and digits are slower)
ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
RECAP_WORDS = ("à retenir", "retiens", "récap", "en résumé", "concept", "demain", "abonne", "suis", "commente", "partage", "sauvegarde", "épingl", "prochain")
FILLERS = ("en fait", "du coup", "voilà", "genre", "tout simplement", "basiquement", "n'hésite pas")

def speech_seconds(text: str, cps: float = CPS, speed: float = 1.0, tempo: float = 1.0) -> float:
    weighted = len(text) + 2.0 * sum(ch.isdigit() for ch in text) + 1.5 * sum(len(m) for m in ACRONYM.findall(text))
    return weighted / (cps * float(speed) * float(tempo))

def first_sentence(text: str) -> str:
    m = re.split(r"(?<=[.?!…])\s+", text.strip(), maxsplit=1); return m[0] if m else text

def lint(project, pricing=None, log=print):
    """Prints a table (chars, est. seconds, real seconds if vo/ exists) and findings. Returns the number of warnings."""
    script = project.get("script") or []; v = project["voice"]; tl = project.get("timeline", {}) or {}
    tempo = float((tl.get("audio") or {}).get("vo_tempo", 1.0)); lead, tail = float(tl.get("beat_lead", 0.25)), float(tl.get("beat_tail", 0.2))
    cps = float(v.get("chars_per_second", CPS)); warns = []; infos = []
    if not script: log("script: [] (variante sans voix) - rien à vérifier"); return 0
    log(f"SCRIPT {project.label}  ({len(script)} segments, voix {v.get('voice_id') or '?'} x{v.get('speed', 1.0)}, vo_tempo {tempo}, {cps} car/s)\n")
    log(f"  {'id':<16} {'car':>4} {'mots':>4} {'~s':>5} {'réel':>5}  texte")
    tot_est = tot_real = 0.0; chars = 0
    for i, seg in enumerate(script):
        text = seg["text"]; est = speech_seconds(text, cps, seg.get("speed", v.get("speed", 1.0)), tempo); chars += len(text)
        f = project.dir / "vo" / f"{seg['id']}.mp3"; real = None
        if f.exists():
            try: real = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)])) / tempo
            except Exception: real = None
        tot_est += est; tot_real += real or est
        log(f"  {seg['id']:<16} {len(text):4d} {len(text.split()):4d} {est:5.1f} {(f'{real:5.1f}' if real else '    -')}  {text[:70]}{'…' if len(text) > 70 else ''}")
        if est > 15: warns.append(f"{seg['id']}: ~{est:.0f} s de voix, couper en deux segments (≤ 12-15 s, un visuel par idée)")
        if i == 0:
            fs = first_sentence(text); fe = speech_seconds(fs, cps, 1.0, tempo)
            if fe > 3.5: warns.append(f"accroche : la première phrase dure ~{fe:.1f} s ({len(fs)} car.), viser ≤ 3 s : une image, une question ou un chiffre")
            if not re.search(r"[?!]|\d|jamais|erreur|pourquoi|déjà|vrai", text, re.I): infos.append("accroche : pas de question, chiffre, « erreur », « jamais » ou « déjà » : vérifier qu'elle ouvre une boucle (`promokit hooks`)")
        if re.search(r"\d|https?://|www\.|\.(com|dev|io|fr)\b", text) and not seg.get("display"): infos.append(f"{seg['id']}: chiffres ou URL prononcés : ajouter `display:` avec l'orthographe à afficher (gratuit)")
        for fw in FILLERS:
            if fw in text.lower(): infos.append(f"{seg['id']}: mot de remplissage « {fw} »")
        if i == len(script) - 1 and not any(w in text.lower() for w in RECAP_WORDS): warns.append(f"{seg['id']}: dernier segment sans récap ni appel à l'action (« À retenir : … », numéro du concept, « on continue demain »)")
    acr = sorted({a for seg in script for a in ACRONYM.findall(seg["text"]) if len(a) >= 2 and not a.isdigit()})
    keep = set((project.get("captions") or {}).get("keep") or [])
    missing = [a for a in acr if a not in keep]
    if missing: infos.append(f"sigles prononcés {', '.join(missing[:8])} : vérifier la prononciation MiniMax et les ajouter dans captions.keep s'ils forment une expression")
    n = len(script); total = tot_real + n * (lead + tail); log(f"\n  total voix ~{tot_real:.0f} s + {n} beats × ({lead}+{tail}) s = ~{total:.0f} s de vidéo")
    if total > 65: warns.append(f"~{total:.0f} s : trop long pour un concept TikTok (viser 35-60 s) : supprimer un segment ou raccourcir chaque phrase")
    if total < 25: infos.append(f"~{total:.0f} s : court ; c'est bien si chaque idée a son visuel")
    if not 4 <= n <= 8: infos.append(f"{n} segments : la structure type est 5-7 (accroche, définition, problème, mécanisme, bonne pratique, récap)")
    if pricing:
        try: log(f"  coût voix si tout est régénéré : ~${sum(pricing.tts(v['model'], len(s['text'])) for s in script):.3f} ({chars} caractères)")
        except Exception: pass
    log("")
    for w in warns: log(f"  WARN  {w}")
    for x in infos: log(f"  info  {x}")
    if not warns: log("  OK    aucun blocage ; relire à voix haute avant `promokit vo`")
    return len(warns)

# ----------------------------------------------------------------------------- word timings
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm_word(w: str) -> str:
    return strip_accents(re.sub(r"^[\W_]+|[\W_]+$", "", str(w).replace(" ", " ").split(" ")[0])).lower()

def word_report(project, only=None, log=print):
    """Per-word start times of the generated voice-over (tempo-adjusted), as `from:` values usable in beats."""
    from .assemble import Assembler
    A = Assembler(project, log=lambda *a: None); tl = project.get("timeline", {}) or {}
    tempo = float((tl.get("audio") or {}).get("vo_tempo", 1.0)); lead = float(tl.get("beat_lead", 0.25)); n = 0
    for seg in project.get("script") or []:
        if only and seg["id"] not in only: continue
        f = project.dir / "vo" / f"{seg['id']}.mp3"
        if not f.exists(): log(f"  {seg['id']}: pas de voix générée (promokit vo)"); continue
        words = A.word_times(f, seg["text"], tempo, display=seg.get("display")); pauses = [(a / tempo, (b or a) / tempo) for a, b in A.speech_pauses(f)]
        L = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)])) / tempo
        log(f"\n{seg['id']}  {L:.2f} s (tempo {tempo})   beat_lead {lead}   pauses: " + ", ".join(f"{a:.2f}-{b:.2f}" for a, b in pauses if 0.1 < a < L - 0.1))
        log(f"  {'mot':<22} {'t voix':>7} {'from':>6}")
        for w, a, b, ph in words: log(f"  {w[:22]:<22} {a:7.2f} {lead + a:6.2f}"); n += 1
    log(f"\nUsage : overlays: [{{id: chip_x, from: \"@certificat\", to: -0.2}}]  (« @mot » = début du mot, « @mot:2 » = 2e occurrence, « @mot.end », « @mot+0.3 »)")
    return n

WORD_REF = re.compile(r"^@([^\s+\-:.]+)(?::(\d+))?(?:\.(end))?([+-]\d+(?:\.\d+)?)?$")

def resolve_word_ref(ref: str, words, what: str = "") -> float:
    """'@mot' | '@mot:2' | '@mot.end' | '@mot+0.3' -> time (s) relative to the start of the voice-over. words: [(word, start, end), ...]."""
    m = WORD_REF.match(str(ref).strip())
    if not m: raise ValueError(f"bad word reference '{ref}' (expected @mot, @mot:2, @mot.end, @mot+0.3)")
    q, nth, end, off = norm_word(m.group(1)), int(m.group(2) or 1), m.group(3), float(m.group(4) or 0)
    hits = [(a, b) for w, a, b in words if norm_word(w) == q] or [(a, b) for w, a, b in words if norm_word(w).startswith(q)]
    if len(hits) < nth: raise LookupError(f"{what}: word '{m.group(1)}' (occurrence {nth}) not found in the voice-over; words: " + " ".join(w for w, _, _ in words))
    a, b = hits[nth - 1]; return (b if end else a) + off

# ----------------------------------------------------------------------------- concept scaffolding
def concept_lookup(kit: pathlib.Path, num: int):
    """Row `num` of 100-concepts-backend-tiktok.md (| n | Concept | Angle |) -> (title, angle, section) or None."""
    f = kit / "100-concepts-backend-tiktok.md"
    if not f.exists(): return None
    section = ""
    for line in f.read_text().splitlines():
        if line.startswith("### "): section = line[4:].strip()
        m = re.match(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
        if m and int(m.group(1)) == num: return m.group(2).replace("`", ""), m.group(3).replace("`", ""), section
    return None

def title_lines(title: str) -> str:
    """'REST vs GraphQL' -> 'REST\\nvs GRAPHQL' (two short lines for the hook title, YAML-escaped)."""
    t = title.strip()
    for sep in (" vs ", " contre ", " — ", " : ", " - "):
        if sep in t: a, b = t.split(sep, 1); return f"{a.upper()}\\n{'vs ' if sep in (' vs ', ' contre ') else ''}{b.upper()}"
    ws = t.split()
    if len(t) > 14 and len(ws) > 1: k = len(ws) // 2; return " ".join(ws[:k]).upper() + "\\n" + " ".join(ws[k:]).upper()
    return t.upper()

def scaffold(kit: pathlib.Path, name: str, title: str, angle: str = "", num: int | None = None, series: str = "100 Concepts Backend", handle: str = "@starland9", template: str = "learning-tiktok", log=print):
    src = kit / "templates" / template; dst = kit / "projects" / name
    if not src.exists(): raise FileNotFoundError(f"template {src} missing")
    if dst.exists(): raise FileExistsError(f"{dst} already exists")
    shutil.copytree(src, dst)
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    rep = {"__NAME__": name, "__SLUG__": slug, "__TITLE__": title, "__TITLE_LINES__": title_lines(title), "__ANGLE__": angle or "", "__NUM__": str(num or "?"),
           "__SERIES__": series, "__HANDLE__": handle, "__CONCEPT_LABEL__": f"Concept {num}/100 · {title}" if num else title}
    for f in dst.rglob("*"):
        if f.is_file() and f.suffix in (".yaml", ".txt", ".md"):
            s = f.read_text()
            for k, v_ in rep.items(): s = s.replace(k, v_)
            f.write_text(s)
    log(f"created {dst}  ({title}{' · ' + angle if angle else ''})")
    log(f"  1) hooks : promokit hooks --slot concept=\"{title}\"")
    log(f"  2) écrire script + display, puis : promokit script {name}")
    log(f"  3) prompts H3 (skill h3-prompting, section motion design) dans {dst / 'prompts'}")
    log(f"  4) gratuit : promokit overlays {name} --variant gratuit && promokit assemble {name} --variant gratuit --proxies")
    log(f"  5) payant : promokit plan {name} → vo --yes → clips --yes --only A_hook → … → assemble --sub --proxies")
    return dst
