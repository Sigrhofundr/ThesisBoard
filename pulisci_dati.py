#!/usr/bin/env python3
"""Rimuove i dati generati e le cache di ThesisBoard.

Esempi:
    python pulisci_dati.py
    python pulisci_dati.py tesi
    python pulisci_dati.py jobs --yes
    python pulisci_dati.py tesi --dry-run
"""

import argparse
import shutil
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

TARGETS = {
    "tesi": (
        "tesi",
        (BASE_DIR / "data.js", BASE_DIR / "dettagli_html"),
    ),
    "jobs": (
        "job",
        (BASE_DIR / "jobs_data.js", BASE_DIR / "dettagli_jobs"),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rimuove i dati generati e le cache di tesi o job."
    )
    parser.add_argument(
        "tipo",
        nargs="?",
        choices=tuple(TARGETS),
        help="dominio da pulire: tesi oppure jobs; se omesso viene chiesto interattivamente",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="conferma la cancellazione senza prompt (utile per script e automazioni)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra cosa verrebbe cancellato senza modificare file",
    )
    return parser.parse_args()


def choose_target() -> str:
    print("Seleziona i dati da rimuovere:")
    print("  1) Tesi (data.js e dettagli_html/)")
    print("  2) Job (jobs_data.js e dettagli_jobs/)")

    while True:
        choice = input("Scelta [1/2]: ").strip().lower()
        if choice in {"1", "tesi"}:
            return "tesi"
        if choice in {"2", "jobs", "job"}:
            return "jobs"
        print("[ERRORE] Inserisci 1 per le tesi oppure 2 per i job.")


def existing_paths(tipo: str) -> list[Path]:
    return [path for path in TARGETS[tipo][1] if path.exists()]


def describe_paths(paths: list[Path]) -> None:
    if not paths:
        print("  Nessun dato trovato.")
        return

    for path in paths:
        label = f"{path.relative_to(BASE_DIR)}/" if path.is_dir() else str(path.relative_to(BASE_DIR))
        print(f"  - {label}")


def remove_paths(paths: list[Path]) -> None:
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def main() -> int:
    args = parse_args()
    tipo = args.tipo or choose_target()
    paths = existing_paths(tipo)
    label = TARGETS[tipo][0]

    print(f"\nDati selezionati: {label}")
    describe_paths(paths)

    if args.dry_run:
        print("[DRY-RUN] Nessun file è stato modificato.")
        return 0

    if not paths:
        return 0

    if not args.yes:
        print("\nATTENZIONE: questa operazione elimina definitivamente i dati selezionati.")
        confirmation = input("Digita ELIMINA per confermare: ").strip()
        if confirmation != "ELIMINA":
            print("[INFO] Operazione annullata.")
            return 0

    try:
        remove_paths(paths)
    except OSError as error:
        print(f"[ERRORE] Impossibile completare la cancellazione: {error}", file=sys.stderr)
        return 1

    print(f"[OK] Dati {label} rimossi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())