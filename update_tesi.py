#!/usr/bin/env python3
"""
update_tesi.py - Script unificato per scaricare e aggiornare le proposte di tesi.

Utilizzo:
    python update_tesi.py

Il primo avvio chiede il cookie di sessione del Portale della Didattica.
Esecuzioni successive rilevano automaticamente .env (POLITO_COOKIE).
"""

import os
import re
import sys
import argparse
import json
import time
import hashlib
import requests
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# ── Configurazione ────────────────────────────────────────────────────────────
BASE_URL       = "https://didattica.polito.it"
LIST_URL       = f"{BASE_URL}/pls/portal30/sviluppo.pagine_studenti.tesi_proposte_cds"
DETAIL_URL     = f"{BASE_URL}/pls/portal30/sviluppo.tesi_proposte.visualizza?p_id={{pid}}"
HTML_DIR       = os.path.join(os.path.dirname(__file__), "dettagli_html")
COOKIE_FILE    = os.path.join(os.path.dirname(__file__), "cookie.txt")
ENV_FILE       = os.path.join(os.path.dirname(__file__), ".env")
ENV_COOKIE_KEY = "POLITO_COOKIE"
JS_FILE        = os.path.join(os.path.dirname(__file__), "data.js")
CACHE_META_FILE= os.path.join(HTML_DIR, "_cache_meta.json")
REQUEST_DELAY  = 1  # secondi tra le richieste

# ── Keyword automatiche ───────────────────────────────────────────────────────
KEYWORD_PATTERNS = {
    "Intelligenza Artificiale": ["machine learning", "deep learning", "neural network", "ai", "artificial intelligence", "llm", "nlp", "natural language"],
    "Computer Vision": ["image recognition", "computer vision", "object detection", "visual", "image segmentation", "cnn"],
    "Robotica": ["robot", "robotics", "autonomous", "drone", "uav", "manipulation", "locomotion"],
    "Cybersecurity": ["security", "attack", "malware", "cryptograph", "vulnerabilit", "intrusion", "cyber"],
    "Reti": ["network", "networking", "5g", "wireless", "routing", "protocol", "telecommunication", "rete"],
    "Cloud & Edge": ["cloud", "edge computing", "fog", "serverless", "kubernetes", "docker", "microservice"],
    "IoT": ["iot", "embedded", "sensor", "mqtt", "smart home", "wearable", "internet of things"],
    "Data Science": ["data", "analytics", "database", "big data", "prediction", "forecast", "statistical"],
    "Software Engineering": ["software", "agile", "testing", "devops", "web development", "mobile app", "flutter", "react"],
    "Ottimizzazione": ["optimization", "ottimizzaz", "genetic algorithm", "scheduling", "planning", "heuristic"],
    "Energia": ["energy", "photovoltaic", "solar", "wind", "battery", "electric vehicle", "power"],
    "Biomedica": ["medical", "health", "clinical", "biomedical", "eeg", "ecg", "brain", "patient"],
    "Chimica": ["chemical", "polymer", "material", "synthesis", "catalyst", "chemistry"],
    "Meccanica": ["mechanical", "structural", "stress", "fracture", "finite element", "fem", "cfd"],
    "Automotive": ["automotive", "vehicle", "autonomous driving", "lidar", "adas"],
    "Ambiente": ["environmental", "sustainability", "emission", "pollution", "climate"],
}

def get_auto_keywords(text: str) -> list[str]:
    """Genera keyword automatiche analizzando il testo."""
    text_lower = text.lower()
    found = []
    for kw, patterns in KEYWORD_PATTERNS.items():
        if any(p in text_lower for p in patterns):
            found.append(kw)
    return found

def normalize_text(value: str) -> str:
    """Rimuove spazi, tab e newline multipli riducendoli ad un singolo spazio."""
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n|\r", "\n", (value or ""))).strip()

def clean_long_text(value: str) -> str:
    """Normalizza testi lunghi (descrizione, competenze): preserva i a-capo semantici
    ma rimuove spazi/tab superflui all'interno di ogni riga."""
    lines = (value or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    cleaned = []
    for line in lines:
        # rimuove spazi e tab multipli interni, poi strip di riga
        clean_line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned.append(clean_line)
    # collassa più righe vuote consecutive in una sola
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return result.strip()

def split_multi(value: str) -> list[str]:
    """Divide campi multipli con delimitatori eterogenei in modo robusto."""
    clean = (value or "").replace("\r", "\n")
    parts = re.split(r"\n+|\s{2,}|[;,]", clean)
    return [p.strip() for p in parts if p and p.strip()]

def parse_expiry_date(value: str):
    """Estrae una data valida da formati comuni presenti nel portale."""
    val = normalize_text(value)
    if not val:
        return None

    candidates = [val]
    m = re.search(r"(\d{2}/\d{2}/\d{4})", val)
    if m:
        candidates.append(m.group(1))
    m = re.search(r"(\d{4}-\d{2}-\d{2})", val)
    if m:
        candidates.append(m.group(1))

    for c in candidates:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(c, fmt).date()
            except ValueError:
                pass
    return None

def extract_cached_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    tit = soup.find("td", class_="rightTit")
    if not tit:
        return ""
    return normalize_text(tit.get_text(" "))

def extract_last_update_marker(html: str) -> str:
    """Prova a estrarre un campo di ultimo aggiornamento dalla pagina, se presente."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            key = normalize_text(cells[0].get_text(" ")).lower()
            if any(k in key for k in ("aggiornamento", "last update", "ultimo update")):
                return normalize_text(cells[1].get_text(" "))

    text = soup.get_text(" ", strip=True)
    m = re.search(r"(?:Ultimo\s+aggiornamento|Data\s+aggiornamento|Last\s+update)\s*:?\s*([^\s].{0,40})", text, re.IGNORECASE)
    if m:
        return normalize_text(m.group(1))
    return ""

def html_digest(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()

def load_cache_meta() -> dict:
    if not os.path.exists(CACHE_META_FILE):
        return {}
    try:
        with open(CACHE_META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def save_cache_meta(meta: dict) -> None:
    os.makedirs(HTML_DIR, exist_ok=True)
    with open(CACHE_META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def load_cookie_from_env_file() -> str:
    if not os.path.exists(ENV_FILE):
        return ""
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                row = line.strip()
                if not row or row.startswith("#") or "=" not in row:
                    continue
                key, val = row.split("=", 1)
                if key.strip() == ENV_COOKIE_KEY:
                    return val.strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""

def write_cookie_to_env_file(cookie: str) -> None:
    lines = []
    updated = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    out = []
    for line in lines:
        raw = line.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            key = raw.split("=", 1)[0].strip()
            if key == ENV_COOKIE_KEY:
                out.append(f"{ENV_COOKIE_KEY}={cookie}\n")
                updated = True
                continue
        out.append(line)

    if not updated:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.append(f"{ENV_COOKIE_KEY}={cookie}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(out)

# ── Cookie management ─────────────────────────────────────────────────────────
def load_or_ask_cookie() -> str:
    cookie = os.getenv(ENV_COOKIE_KEY, "").strip()
    if cookie:
        print(f"[INFO] Cookie caricato dalla variabile d'ambiente {ENV_COOKIE_KEY}")
        return cookie

    cookie = load_cookie_from_env_file().strip()
    if cookie:
        print(f"[INFO] Cookie caricato da {ENV_FILE}")
        print("[INFO] Se la sessione è scaduta, aggiorna POLITO_COOKIE in .env.")
        return cookie

    # Compatibilità con versione precedente: migra da cookie.txt a .env
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie = f.read().strip()
        if cookie:
            write_cookie_to_env_file(cookie)
            try:
                os.remove(COOKIE_FILE)
                print(f"[INFO] Cookie migrato da {COOKIE_FILE} a {ENV_FILE} e file legacy rimosso.")
            except OSError:
                print(f"[INFO] Cookie migrato da {COOKIE_FILE} a {ENV_FILE}.")
            return cookie

    print("=" * 60)
    print("Inserisci il Cookie di sessione del Portale della Didattica.")
    print("Puoi trovarlo aprendo https://didattica.polito.it nel browser,")
    print("premendo F12 → Application → Cookies → copia il valore del cookie.")
    print("=" * 60)
    cookie = input("Cookie: ").strip()
    if not cookie:
        print("[ERRORE] Cookie non fornito. Uscita.")
        sys.exit(1)
    write_cookie_to_env_file(cookie)
    print(f"[INFO] Cookie salvato in {ENV_FILE} ({ENV_COOKIE_KEY}).")
    return cookie

def make_headers(cookie: str) -> dict:
    return {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

# ── Download lista ────────────────────────────────────────────────────────────
def fetch_list(cookie: str) -> list[dict]:
    """Scarica la pagina elenco tesi e restituisce lista di {pid, titolo}."""
    print(f"[INFO] Scaricamento lista tesi da {LIST_URL}...")
    resp = requests.get(LIST_URL, headers=make_headers(cookie), timeout=30)
    if resp.status_code != 200:
        print(f"[ERRORE] Status {resp.status_code} scaricando la lista. Cookie valido?")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.select("a.policorpolink")

    if not links:
        print("[ERRORE] Nessun link trovato. Forse il cookie è scaduto o la struttura è cambiata.")
        sys.exit(1)

    tesi = []
    for a in links:
        href = a.get("href", "")
        m = re.search(r"p_id=(\d+)", href)
        if m:
            tesi.append({"pid": m.group(1), "titolo_lista": a.text.strip()})

    print(f"[INFO] Trovate {len(tesi)} tesi in lista.")
    return tesi

# ── Download singola tesi ─────────────────────────────────────────────────────
def fetch_detail_html(
    pid: str,
    cookie: str,
    expected_title: str = "",
    check_updates: bool = False,
) -> tuple[str | None, bool, bool]:
    """Scarica la pagina di dettaglio di una tesi e la salva su disco."""
    os.makedirs(HTML_DIR, exist_ok=True)
    fpath = os.path.join(HTML_DIR, f"{pid}.html")

    if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            cached_html = f.read()

        cached_title = extract_cached_title(cached_html)
        title_matches = (not expected_title) or (cached_title and normalize_text(expected_title) == cached_title)

        if title_matches and not check_updates:
            return cached_html, True, False

        # Modalità check-updates: confronta marker di aggiornamento (se presente) o hash contenuto.
        url = DETAIL_URL.format(pid=pid)
        try:
            resp = requests.get(url, headers=make_headers(cookie), timeout=20)
            if resp.status_code == 200:
                remote_html = resp.text
                cached_marker = extract_last_update_marker(cached_html)
                remote_marker = extract_last_update_marker(remote_html)
                if cached_marker and remote_marker:
                    changed = cached_marker != remote_marker
                else:
                    changed = html_digest(cached_html) != html_digest(remote_html)

                if changed:
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(remote_html)
                    return remote_html, False, True

                return cached_html, True, False
            print(f"  [WARN] HTTP {resp.status_code} per p_id={pid} durante check aggiornamenti")
        except requests.RequestException as e:
            print(f"  [WARN] Errore rete per p_id={pid} durante check aggiornamenti: {e}")

        # In caso di errore nel check, mantieni cache esistente.
        return cached_html, True, False

    url = DETAIL_URL.format(pid=pid)
    try:
        resp = requests.get(url, headers=make_headers(cookie), timeout=20)
        if resp.status_code == 200:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(resp.text)
            return resp.text, False, False
        else:
            print(f"  [WARN] HTTP {resp.status_code} per p_id={pid}")
    except requests.RequestException as e:
        print(f"  [WARN] Errore rete per p_id={pid}: {e}")
    return None, False, False

# ── Parsing dettaglio ─────────────────────────────────────────────────────────
def parse_detail(html: str, pid: str) -> dict:
    """Estrae campi strutturati dalla pagina di dettaglio."""
    soup = BeautifulSoup(html, "html.parser")

    record = {
        "pid":                 pid,
        "titolo":              "",
        "relatori":            [],
        "parole_chiave_raw":   [],   # parole chiave estratte dal portale
        "keywords":            [],   # parole chiave finali (raw + auto se vuote)
        "tipo_tesi":           "",
        "azienda":             False,
        "estero":              False,
        "scadenza":            "",
        "scaduta":             False,
        "descrizione":         "",
        "competenze_richieste":"",
        "gruppi_ricerca":      [],
        "riferimenti_esterni": "",
        "allegati":            [],
        "link_polito":         DETAIL_URL.format(pid=pid),
    }

    # Titolo
    tit = soup.find("td", class_="rightTit")
    if tit:
        record["titolo"] = re.sub(r"\s+", " ", tit.text).strip()

    table = soup.find("table")
    if not table:
        return record

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        key = normalize_text(cells[0].text.replace("\xa0", "")).lower()
        val_cell = cells[1]
        val_text = normalize_text(val_cell.get_text(" ").replace("\xa0", " "))

        # Alcune pagine riportano "Tesi esterna in azienda/estero" in una riga senza label.
        if not key and val_text:
            val_lower = val_text.lower()
            if "azienda" in val_lower:
                record["azienda"] = True
            if "estero" in val_lower or val_cell.find("img", attrs={"alt": "estero"}):
                record["estero"] = True

        if "riferimenti" in key and "esterni" not in key:
            # Relatori
            record["relatori"] = split_multi(val_text)

        elif "parole chiave" in key or "keyword" in key:
            links_kw = val_cell.find_all("a")
            if links_kw:
                record["parole_chiave_raw"] = [a.text.strip() for a in links_kw if a.text.strip()]
            else:
                record["parole_chiave_raw"] = [k.strip() for k in re.split(r"[,;]", val_text) if k.strip()]

        elif "tipo tesi" in key:
            record["tipo_tesi"] = val_text
            # Azienda
            if "azienda" in val_text.lower():
                record["azienda"] = True
            # Estero: può essere nel testo o segnalato dall'img globe.png
            if "estero" in val_text.lower() or val_cell.find("img", attrs={"alt": "estero"}):
                record["estero"] = True

        elif "descrizione" in key:
            for br in val_cell.find_all("br"):
                br.replace_with("\n")
            record["descrizione"] = clean_long_text(val_cell.get_text())

        elif "competenze" in key or "conoscenze" in key:
            record["competenze_richieste"] = clean_long_text(val_text)

        elif "gruppi di ricerca" in key:
            links_gr = val_cell.find_all("a")
            record["gruppi_ricerca"] = [a.text.strip() for a in links_gr if a.text.strip()]
            if not record["gruppi_ricerca"] and val_text:
                record["gruppi_ricerca"] = split_multi(val_text)

        elif "vedi anche" in key or "riferimenti esterni" in key:
            record["riferimenti_esterni"] = val_text
            links = []
            for a in val_cell.find_all("a", href=True):
                href = normalize_text(a.get("href", ""))
                if not href:
                    continue
                links.append({
                    "label": normalize_text(a.get_text(" ")) or href,
                    "url": urljoin(BASE_URL, href),
                })
            # Rimuovi duplicati preservando l'ordine
            seen = set()
            deduped = []
            for item in links:
                key_link = (item["label"], item["url"])
                if key_link in seen:
                    continue
                seen.add(key_link)
                deduped.append(item)
            record["allegati"] = deduped

        elif "scadenza" in key:
            record["scadenza"] = val_text
            # Parsing data scadenza
            exp_date = parse_expiry_date(val_text)
            if exp_date:
                record["scaduta"] = exp_date < datetime.today().date()

    # Keyword finali: usa quelle del portale se presenti, altrimenti genera automaticamente
    if record["parole_chiave_raw"]:
        record["keywords"] = record["parole_chiave_raw"]
    else:
        combined = record["titolo"] + " " + record["descrizione"]
        record["keywords"] = get_auto_keywords(combined)

    # Normalizzazione difensiva per stabilità lato UI.
    record["relatori"] = [normalize_text(r) for r in record["relatori"] if normalize_text(r)]
    record["gruppi_ricerca"] = [normalize_text(g) for g in record["gruppi_ricerca"] if normalize_text(g)]
    record["keywords"] = [normalize_text(k) for k in record["keywords"] if normalize_text(k)]

    return record

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Aggiorna proposte di tesi e genera data.js")
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Rivalida anche i file già in cache: aggiorna solo le pagine realmente modificate",
    )
    parser.add_argument(
        "--check-updates-active-only",
        action="store_true",
        help="Con --check-updates, rivalida solo le tesi non scadute (usa la cache per saltare le scadute)",
    )
    args = parser.parse_args()

    if args.check_updates_active_only and not args.check_updates:
        print("[WARN] --check-updates-active-only richiede --check-updates: abilito automaticamente --check-updates.")
        args.check_updates = True

    cookie = load_or_ask_cookie()
    cache_meta = load_cache_meta()

    # 1. Scarica lista
    tesi_list_meta = fetch_list(cookie)

    # 2. Scarica dettagli
    records = []
    total = len(tesi_list_meta)
    updated_count = 0
    skipped_expired_count = 0
    for i, meta in enumerate(tesi_list_meta, 1):
        pid = meta["pid"]
        fpath = os.path.join(HTML_DIR, f"{pid}.html")
        already_exists = os.path.exists(fpath) and os.path.getsize(fpath) > 500
        print(f"  [{i}/{total}] Tesi p_id={pid}", end="", flush=True)

        if args.check_updates and args.check_updates_active_only and already_exists:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                cached_html = f.read()
            cached_record = parse_detail(cached_html, pid)
            if not cached_record["titolo"]:
                cached_record["titolo"] = meta["titolo_lista"]

            if cached_record["scaduta"]:
                skipped_expired_count += 1
                records.append(cached_record)
                cache_meta[pid] = {
                    "digest": html_digest(cached_html),
                    "last_update_marker": extract_last_update_marker(cached_html),
                    "scadenza": cached_record.get("scadenza", ""),
                    "scaduta": cached_record.get("scaduta", False),
                    "checked_at": datetime.now().isoformat(timespec="seconds"),
                }
                print(" - OK (cached, scaduta - check saltato)")
                continue

        html, used_cache, was_updated = fetch_detail_html(
            pid,
            cookie,
            expected_title=meta.get("titolo_lista", ""),
            check_updates=args.check_updates,
        )
        if html is None:
            print(" - SKIP (errore download)")
            records.append({
                "pid": pid, "titolo": meta["titolo_lista"],
                "relatori": [], "keywords": [], "tipo_tesi": "",
                "azienda": False, "estero": False,
                "scadenza": "", "scaduta": False,
                "descrizione": "", "competenze_richieste": "",
                "gruppi_ricerca": [], "riferimenti_esterni": "",
                "allegati": [],
                "link_polito": DETAIL_URL.format(pid=pid),
            })
            if not already_exists:
                time.sleep(REQUEST_DELAY)
            continue

        record = parse_detail(html, pid)
        if not record["titolo"]:
            record["titolo"] = meta["titolo_lista"]
        records.append(record)

        cache_meta[pid] = {
            "digest": html_digest(html),
            "last_update_marker": extract_last_update_marker(html),
            "scadenza": record.get("scadenza", ""),
            "scaduta": record.get("scaduta", False),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

        if was_updated:
            updated_count += 1
            status = "aggiornata"
        else:
            status = "cached" if used_cache else "scaricata"
        print(f" - OK ({status})")
        if not used_cache:
            time.sleep(REQUEST_DELAY)

    save_cache_meta(cache_meta)

    # 3. Carica i PID presenti nel data.js precedente per determinare NEW/UPDATED
    prev_pids: set[str] = set()
    prev_data_by_pid: dict[str, dict] = {}
    is_first_scan = not os.path.exists(JS_FILE)
    if not is_first_scan:
        try:
            with open(JS_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            # Estrai il JSON dal file JS (rimuovi 'const tesiData = ' e ';')
            json_str = re.sub(r"^\s*const\s+\w+\s*=\s*|;\s*$", "", raw, flags=re.DOTALL).strip()
            prev_list = json.loads(json_str)
            for item in prev_list:
                pid_val = str(item.get("pid", ""))
                if pid_val:
                    prev_pids.add(pid_val)
                    prev_data_by_pid[pid_val] = item
        except Exception as e:
            print(f"[WARN] Impossibile caricare data.js precedente per confronto: {e}")
            is_first_scan = True

    # 4. Genera data.js con flag is_new / is_updated
    js_records = []
    new_count = upd_count = 0
    for r in records:
        jr = dict(r)
        jr.pop("parole_chiave_raw", None)
        pid_str = str(r.get("pid", ""))

        if is_first_scan:
            jr["is_new"] = False
            jr["is_updated"] = False
        elif pid_str not in prev_pids:
            jr["is_new"] = True
            jr["is_updated"] = False
            new_count += 1
        else:
            # Controlla se alcuni campi rilevanti sono cambiati
            prev = prev_data_by_pid[pid_str]
            changed_fields = ("titolo", "tipo_tesi", "scadenza", "descrizione",
                              "competenze_richieste", "relatori", "keywords")
            was_changed = any(
                json.dumps(jr.get(f), sort_keys=True) != json.dumps(prev.get(f), sort_keys=True)
                for f in changed_fields
            )
            jr["is_new"] = False
            jr["is_updated"] = was_changed
            if was_changed:
                upd_count += 1

        js_records.append(jr)

    with open(JS_FILE, "w", encoding="utf-8") as f:
        f.write("const tesiData = ")
        json.dump(js_records, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"\n[OK] data.js generato con {len(js_records)} tesi → {JS_FILE}")
    if not is_first_scan:
        print(f"[INFO] Δ scansione: {new_count} nuove, {upd_count} aggiornate.")
    if args.check_updates:
        print(f"[INFO] Check aggiornamenti completato: {updated_count} pagine aggiornate in cache.")
    if args.check_updates and args.check_updates_active_only:
        print(f"[INFO] Check limitato alle non scadute: {skipped_expired_count} tesi scadute saltate.")
    print("[OK] Apri index.html per visualizzare le tesi aggiornate.")

if __name__ == "__main__":
    main()
