#!/usr/bin/env python3
"""
update_jobs.py - Script unificato per scaricare e aggiornare le offerte di lavoro.

Utilizzo:
    python update_jobs.py

Il primo avvio chiede il cookie di sessione del Portale della Didattica.
Esecuzioni successive rilevano automaticamente .env (POLITO_COOKIE).
"""

import os
import sys
import argparse
import json
import time
import requests

# ── Configurazione ────────────────────────────────────────────────────────────
BASE_URL       = "https://didattica.polito.it"
LIST_URL       = f"{BASE_URL}/pls/portal30/stagejob.ng_job.json_stud"
DETAIL_URL     = f"{BASE_URL}/pls/portal30/stagejob.ng_job.dati_job?p_cod_job={{cod}}"
JSON_DIR       = os.path.join(os.path.dirname(__file__), "dettagli_jobs")
ENV_FILE       = os.path.join(os.path.dirname(__file__), ".env")
ENV_COOKIE_KEY = "POLITO_COOKIE"
JS_FILE        = os.path.join(os.path.dirname(__file__), "jobs_data.js")
REQUEST_DELAY  = 0.5  # secondi tra le richieste

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

def load_or_ask_cookie() -> str:
    cookie = os.getenv(ENV_COOKIE_KEY, "").strip()
    if cookie:
        print(f"[INFO] Cookie caricato dalla variabile d'ambiente {ENV_COOKIE_KEY}")
        return cookie

    cookie = load_cookie_from_env_file().strip()
    if cookie:
        print(f"[INFO] Cookie caricato da {ENV_FILE}")
        return cookie

    print("=" * 60)
    print("Inserisci il Cookie di sessione del Portale della Didattica.")
    print("=" * 60)
    cookie = input("Cookie: ").strip()
    if not cookie:
        print("[ERRORE] Cookie non fornito. Uscita.")
        sys.exit(1)
    write_cookie_to_env_file(cookie)
    return cookie

def make_headers(cookie: str) -> dict:
    return {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://didattica.polito.it",
        "Referer": "https://didattica.polito.it/pls/portal30/sviluppo.pagine_studenti.offerte_lavoro"
    }

def fetch_list(cookie: str, title_id: str = "68") -> list[dict]:
    print(f"[INFO] Scaricamento lista lavori...")
    payload = f"liv=2&condiz=0&tit={title_id}"
    resp = requests.post(LIST_URL, headers=make_headers(cookie), data=payload, timeout=30)
    if resp.status_code != 200:
        print(f"[ERRORE] Status {resp.status_code} scaricando la lista. Cookie valido?")
        sys.exit(1)
    
    try:
        data = resp.json()
        jobs = data.get("data", [])
        print(f"[INFO] Trovati {len(jobs)} lavori in lista.")
        return jobs
    except json.JSONDecodeError:
        print("[ERRORE] Risposta non in formato JSON. Cookie probabilmente scaduto.")
        sys.exit(1)

def fetch_detail(cod: str, cookie: str, force_update: bool = False) -> dict:
    os.makedirs(JSON_DIR, exist_ok=True)
    fpath = os.path.join(JSON_DIR, f"{cod}.json")
    
    if not force_update and os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
            
    url = DETAIL_URL.format(cod=cod)
    try:
        resp = requests.get(url, headers=make_headers(cookie), timeout=20)
        if resp.status_code == 200:
            detail_data = resp.json()
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(detail_data, f, ensure_ascii=False, indent=2)
            return detail_data
        else:
            print(f"  [WARN] HTTP {resp.status_code} per cod={cod}")
    except requests.RequestException as e:
        print(f"  [WARN] Errore rete per cod={cod}: {e}")
    except json.JSONDecodeError:
        print(f"  [WARN] Dettaglio per cod={cod} non è JSON valido.")
        
    return {}

def get_corsi(cookie: str) -> list[dict]:
    corsi_file = os.path.join(JSON_DIR, "corsi.json")
    corsi = []

    if os.path.exists(corsi_file):
        try:
            with open(corsi_file, "r", encoding="utf-8") as f:
                corsi = json.load(f)
        except Exception as e:
            print(f"[WARN] Errore lettura {corsi_file}: {e}")

    if not corsi:
        print("[INFO] Recupero la lista dei corsi di laurea disponibili dal portale...")
        headers = {
            "Cookie": cookie,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0"
        }

        for liv in [1, 2]:
            url = f"https://didattica.polito.it/pls/portal30/stagejob.ng_job.list_titoli?term=&liv={liv}"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    liv_name = "Triennale" if liv == 1 else "Magistrale"
                    for c in resp.json():
                        c['liv_name'] = liv_name
                        corsi.append(c)
            except Exception as e:
                print(f"  [WARN] Errore recupero corsi livello {liv}: {e}")
        
        if corsi:
            os.makedirs(JSON_DIR, exist_ok=True)
            with open(corsi_file, "w", encoding="utf-8") as f:
                json.dump(corsi, f, ensure_ascii=False, indent=2)

    return corsi

def print_corsi_list(corsi: list[dict]):
    print("\n" + "=" * 70)
    print(" ELENCO CORSI DI LAUREA DISPONIBILI (Politecnico di Torino)")
    print("=" * 70)
    for liv_name in ["Magistrale", "Triennale"]:
        subset = [c for c in corsi if c.get("liv_name") == liv_name]
        if subset:
            print(f"\n--- {liv_name.upper()} ({len(subset)} corsi) ---")
            for c in subset:
                print(f"  ID: {str(c['id_tit']):<6} | {c['nome_tit']}")
    print("=" * 70 + "\n")

def select_corso(cookie: str) -> str:
    corsi = get_corsi(cookie)

    if not corsi:
        print("[WARN] Impossibile recuperare i corsi. Uso Ingegneria Informatica (68) di default.")
        return "68"

    print("\n" + "=" * 65)
    print(" Selezione Corso di Laurea")
    print("=" * 65)
    print(" Opzioni:")
    print("  • Digita una parola chiave per cercare (es. 'informatica', 'gestionale')")
    print("  • Digita 'tutti' per mostrare l'elenco completo numerato")
    print("  • Premi INVIO per selezionare il default (Ingegneria Informatica Magistrale)")
    print("=" * 65)

    query = input("\nCerca corso / 'tutti' / INVIO (default): ").strip().lower()

    if not query:
        return "68"

    if query in ["tutti", "all", "*"]:
        risultati = corsi
    else:
        risultati = [c for c in corsi if query in c.get('nome_tit', '').lower()]

    if not risultati:
        print("[WARN] Nessun corso trovato con quella ricerca. Uso Ingegneria Informatica (68) di default.")
        return "68"

    print(f"\nCorsi trovati ({len(risultati)}):")
    for i, c in enumerate(risultati, 1):
        print(f"  {i:>3}) [{c['liv_name']}] {c['nome_tit']} (ID: {c['id_tit']})")

    while True:
        scelta = input(f"\nScegli un numero (1-{len(risultati)}) oppure premi INVIO per default: ").strip()
        if not scelta:
            return "68"
        if scelta.isdigit() and 1 <= int(scelta) <= len(risultati):
            scelto = risultati[int(scelta)-1]
            print(f"[INFO] Hai selezionato: {scelto['nome_tit']} [{scelto['liv_name']}] (ID: {scelto['id_tit']})")
            return str(scelto['id_tit'])
        print("[ERRORE] Scelta non valida.")


def main():
    parser = argparse.ArgumentParser(description="Aggiorna offerte di lavoro e genera jobs_data.js")
    parser.add_argument("--force-update", action="store_true", help="Riscarica tutti i dettagli anche se in cache")
    parser.add_argument("--corso", type=str, default="ask", help="ID del corso di studi (default: ask - seleziona interattivamente)")
    parser.add_argument("--list-corsi", action="store_true", help="Mostra l'elenco completo di tutti i corsi di laurea disponibili ed esce")
    args = parser.parse_args()

    cookie = load_or_ask_cookie()

    if args.list_corsi:
        corsi = get_corsi(cookie)
        print_corsi_list(corsi)
        sys.exit(0)

    titolo_id = args.corso
    if titolo_id == "ask":
        titolo_id = select_corso(cookie)

    jobs_list = fetch_list(cookie, title_id=titolo_id)

    # Carica i PID precedenti se esistono
    prev_jobs = {}
    if os.path.exists(JS_FILE):
        try:
            with open(JS_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            json_str = raw.replace("const jobsData = ", "").strip().rstrip(";")
            prev_list = json.loads(json_str)
            for j in prev_list:
                prev_jobs[str(j.get("cod_job", ""))] = j
        except Exception:
            pass

    records = []
    new_count = 0
    updated_count = 0
    
    for i, job_summary in enumerate(jobs_list, 1):
        cod = str(job_summary.get("cod_job"))
        print(f"  [{i}/{len(jobs_list)}] Lavoro cod={cod}", end="", flush=True)
        
        cached = os.path.exists(os.path.join(JSON_DIR, f"{cod}.json"))
        detail = fetch_detail(cod, cookie, args.force_update)
        
        if not cached or args.force_update:
            print(" - SCARICATO")
            time.sleep(REQUEST_DELAY)
        else:
            print(" - CACHE")
            
        # Unione dei dati sommario e dettaglio
        full_job = {**job_summary, **detail}
        
        if cod not in prev_jobs:
            full_job["is_new"] = True
            full_job["is_updated"] = False
            new_count += 1
        else:
            full_job["is_new"] = False
            # Check for changes in key fields? For now let's just mark false
            full_job["is_updated"] = False

        records.append(full_job)

    with open(JS_FILE, "w", encoding="utf-8") as f:
        f.write("const jobsData = ")
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"\n[OK] jobs_data.js generato con {len(records)} offerte di lavoro.")
    print(f"[INFO] Δ scansione: {new_count} nuove offerte.")

if __name__ == "__main__":
    main()
