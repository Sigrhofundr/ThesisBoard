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
import json
import time
import requests
from datetime import datetime
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
    return re.sub(r"\s+", " ", (value or "")).strip()

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
def fetch_detail_html(pid: str, cookie: str, expected_title: str = "") -> tuple[str | None, bool]:
    """Scarica la pagina di dettaglio di una tesi e la salva su disco."""
    os.makedirs(HTML_DIR, exist_ok=True)
    fpath = os.path.join(HTML_DIR, f"{pid}.html")

    if os.path.exists(fpath) and os.path.getsize(fpath) > 500:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            cached_html = f.read()

        if expected_title:
            cached_title = extract_cached_title(cached_html)
            # Resume intelligente: se il titolo lista coincide col cached, saltiamo il download.
            if cached_title and normalize_text(expected_title) == cached_title:
                return cached_html, True
        else:
            return cached_html, True

    url = DETAIL_URL.format(pid=pid)
    try:
        resp = requests.get(url, headers=make_headers(cookie), timeout=20)
        if resp.status_code == 200:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(resp.text)
            return resp.text, False
        else:
            print(f"  [WARN] HTTP {resp.status_code} per p_id={pid}")
    except requests.RequestException as e:
        print(f"  [WARN] Errore rete per p_id={pid}: {e}")
    return None, False

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
            record["descrizione"] = val_cell.get_text().strip()

        elif "competenze" in key or "conoscenze" in key:
            record["competenze_richieste"] = val_text

        elif "gruppi di ricerca" in key:
            links_gr = val_cell.find_all("a")
            record["gruppi_ricerca"] = [a.text.strip() for a in links_gr if a.text.strip()]
            if not record["gruppi_ricerca"] and val_text:
                record["gruppi_ricerca"] = split_multi(val_text)

        elif "vedi anche" in key or "riferimenti esterni" in key:
            record["riferimenti_esterni"] = val_text

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
    cookie = load_or_ask_cookie()

    # 1. Scarica lista
    tesi_list_meta = fetch_list(cookie)

    # 2. Scarica dettagli
    records = []
    total = len(tesi_list_meta)
    for i, meta in enumerate(tesi_list_meta, 1):
        pid = meta["pid"]
        fpath = os.path.join(HTML_DIR, f"{pid}.html")
        already_exists = os.path.exists(fpath) and os.path.getsize(fpath) > 500
        print(f"  [{i}/{total}] Tesi p_id={pid}", end="", flush=True)

        html, used_cache = fetch_detail_html(pid, cookie, expected_title=meta.get("titolo_lista", ""))
        if html is None:
            print(" - SKIP (errore download)")
            records.append({
                "pid": pid, "titolo": meta["titolo_lista"],
                "relatori": [], "keywords": [], "tipo_tesi": "",
                "azienda": False, "estero": False,
                "scadenza": "", "scaduta": False,
                "descrizione": "", "competenze_richieste": "",
                "gruppi_ricerca": [], "riferimenti_esterni": "",
                "link_polito": DETAIL_URL.format(pid=pid),
            })
            if not already_exists:
                time.sleep(REQUEST_DELAY)
            continue

        record = parse_detail(html, pid)
        if not record["titolo"]:
            record["titolo"] = meta["titolo_lista"]
        records.append(record)

        status = "cached" if used_cache else "scaricata"
        print(f" - OK ({status})")
        if not used_cache:
            time.sleep(REQUEST_DELAY)

    # 3. Genera data.js
    # Prepara struttura pulita per il JS (rimuovi parole_chiave_raw)
    js_records = []
    for r in records:
        jr = dict(r)
        jr.pop("parole_chiave_raw", None)
        js_records.append(jr)

    with open(JS_FILE, "w", encoding="utf-8") as f:
        f.write("const tesiData = ")
        json.dump(js_records, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"\n[OK] data.js generato con {len(js_records)} tesi → {JS_FILE}")
    print("[OK] Apri index.html per visualizzare le tesi aggiornate.")

if __name__ == "__main__":
    main()
