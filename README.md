# Thesis Proposals Explorer

This project downloads thesis proposals from the Politecnico portal, extracts structured data, and renders a local interactive interface for browsing and filtering proposals.

## What the project does

- Fetches the thesis list and detail pages from the portal (authenticated session required).
- Extracts and normalizes key fields: title, supervisors, thesis type, expiration date, keywords, description, research groups, and external references.
- Generates `data.js` consumed by the frontend.
- Provides a local UI with full-text filters, advanced filters, expiry handling, modal details, and favorites.

## Main files

- `update_tesi.py`: unified update pipeline (download list, download details, parse, generate `data.js`).
- `index.html`: interactive frontend that reads `data.js`.
- `data.js`: generated dataset used by the UI.
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

Sensitive data is loaded from `.env` using the key `POLITO_COOKIE`.

1. Duplicate `.env_example` to `.env`.
2. Set `POLITO_COOKIE` with your current authenticated portal cookie.

Example `.env`:

```env
POLITO_COOKIE=your_real_cookie_value
```

If `.env` is missing, `update_tesi.py` asks for the cookie interactively and stores it in `.env`.

## Usage

Generate/update the dataset:

```bash
python update_tesi.py
```

Then open `index.html` in your browser.

## UI features

- Text search by title
- Text search by supervisor
- Text search by keyword (partial match)
- Filters by thesis type and research group
- Expiry filter (all, active, expired)
- Company and abroad filters
- Expired badge and visual desaturation for expired cards
- Detail modal with extended fields
- Favorites (persistent in browser `localStorage`) and dedicated favorites section

## Notes

- `data.js` is generated from `update_tesi.py`; rerun the script whenever you want fresh data.
- The detail HTML cache is stored locally in `dettagli_html/` and is ignored by Git.
- Session cookies expire; update `.env` when needed.
