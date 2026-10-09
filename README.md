# Thesis & Job Proposals Explorer (ThesisBoard)

This project downloads thesis proposals and job offers from the Politecnico di Torino student portal, extracts structured data, and renders local interactive interfaces for browsing, filtering, and bookmarking proposals.

## What the project does

### 1. Thesis Proposals (`index.html`)
- Fetches the thesis list and detail pages from the portal (authenticated session required).
- Extracts and normalizes key fields: title, supervisors, thesis type, expiration date, keywords, description, research groups, and external references.
- Generates `data.js` consumed by the frontend.
- Provides a local UI with full-text filters, advanced filters, expiry handling, modal details, and favorites.

### 2. Job Offers (`index_jobs.html`)
- Fetches the official job offers list and full detail specifications via the portal API.
- Normalizes company info, job role/title, location/seats, contract type, compensation details, requirements, and deadlines.
- Cleans HTML markup from descriptions and caches individual job details locally in `dettagli_jobs/`.
- Generates `jobs_data.js` consumed by the dedicated frontend.
- Provides a responsive glassmorphic UI matching the thesis hub with instant search, contract/location filtering, detail modal, and favorites.

## Main files

- **Thesis:**
  - `update_tesi.py`: unified thesis update pipeline (download list, download details, parse, generate `data.js`).
  - `index.html`: interactive frontend that reads `data.js`.
  - `data.js`: generated dataset for thesis proposals.
- **Job Offers:**
  - `update_jobs.py`: unified job offers update pipeline (download list, download details, generate `jobs_data.js`).
  - `index_jobs.html`: interactive frontend that reads `jobs_data.js`.
  - `jobs_data.js`: generated dataset for job offers.
- **Shared / Configuration:**
  - `.env`: local file holding session credentials (`POLITO_COOKIE`).
  - `.env_example`: template for sensitive configuration.

## Requirements

- Python 3.10+
- Python packages:
  - `requests`
  - `beautifulsoup4`

Install dependencies:

```bash
pip install requests beautifulsoup4
```

## Configuration

Sensitive data is loaded from `.env` using the key `POLITO_COOKIE` (shared between thesis and job update scripts).

1. Duplicate `.env_example` to `.env`.
2. Set `POLITO_COOKIE` with your current authenticated portal cookie.

Example `.env`:

```env
POLITO_COOKIE=your_real_cookie_value
```

If `.env` is missing, both `update_tesi.py` and `update_jobs.py` will prompt for the cookie interactively and save it automatically to `.env`.

## Usage

### Updating Thesis Proposals
```bash
python update_tesi.py
```
Then open `index.html` in your browser.

---

### Updating Job Offers
```bash
python update_jobs.py
```
When run, the script checks local cache `dettagli_jobs/corsi.json` (or fetches from the portal if missing) and presents an interactive prompt to filter or choose a course.

**Ways to view and select degree courses:**
1. **List all courses in terminal:**
   ```bash
   python update_jobs.py --list-corsi
   ```
   Displays all available courses (both Triennale and Magistrale) grouped with their respective IDs.
2. **Interactive prompt:**
   Run `python update_jobs.py` and:
   - Type a keyword (e.g. `informatica` or `gestionale`) to filter.
   - Type `tutti` to show the full numbered list and pick by number.
   - Press `Enter` to proceed with the default (*Ingegneria Informatica Magistrale*).
3. **Inspect the raw file:**
   Open `dettagli_jobs/corsi.json` to view the full JSON list with `id_tit` and `nome_tit`.
4. **Direct ID selection:**
   Pass `--corso <ID>` to skip prompts completely (e.g., `68` for Computer Engineering):
   ```bash
   python update_jobs.py --corso 68
   ```

Then open `index_jobs.html` in your browser.

### Removing downloaded data
To remove the generated dataset and local cache for one domain, run:

```bash
python pulisci_dati.py tesi
python pulisci_dati.py jobs
```

Without an argument, the script presents a menu. It always asks for the exact confirmation `ELIMINA`; use `--yes` only in automated scripts. Use `--dry-run` to preview the files that would be removed.

## UI Features

### Thesis UI (`index.html`)
- Text search by title, supervisor, and keywords
- Filters by thesis type, research group, company, and abroad availability
- Expiry filter (all, active, expired) with visual status badges
- Detail modal with extended fields and links
- Favorites system (persisted in browser `localStorage`)

### Job Offers UI (`index_jobs.html`)
- Text search by role/title, company, description, and workplace location
- Filters by contract type (e.g. Tempo indeterminato, Stage, Apprendistato) and location
- Expiry status filter (all, active, expired)
- Interactive bidirectional sorting toolbar mirroring the student portal (Azienda, Oggetto, Sede, Data inserzione, Validità offerta)
- Extended detail modal (job description, candidate requirements, compensation/benefits, locations, link to official portal page)
- Favorites system with dedicated favorites view (persisted in browser `localStorage`)

## Notes

- Both `data.js` and `jobs_data.js` are generated locally and ignored by Git.
- Details are cached locally (`dettagli_html/` for thesis, `dettagli_jobs/` for jobs) to avoid re-downloading unchanged items.
- Politecnico portal session cookies expire periodically; update `POLITO_COOKIE` in `.env` when requests return authentication errors.

