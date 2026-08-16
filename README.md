# Zain Bazaar

Storefront and rate board for Zain Bazaar — Max Nursery Garden Road, Manal, Kannur.
Flask + SQLite. No build step, no Node, no framework on the frontend.

## What's here

| Path | What it is |
|---|---|
| `/` | Customer-facing shop. Rates board, order builder, WhatsApp handoff. |
| `/admin` | Password-protected. Edit prices, hide out-of-stock items, add items, see recent orders. |
| `/login` | Sign-in for `/admin`. |
| `/api/order` | Logs the basket when a customer sends their list to WhatsApp. |

Data lives in `zain.db`, created automatically on first run and seeded with a
sample rate list. **Replace the seed prices with the shop's real ones** — either
edit `SEED_ITEMS` in `app.py` before the first run, or just edit them in `/admin`
afterwards.

## Run it locally

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac / Linux

pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 — and http://127.0.0.1:5000/admin for the rate board.
Default admin password is `zain2026`.

## Before it goes live

Three things, all set as environment variables on the host — never committed:

```
SECRET_KEY=<a long random string>
ADMIN_PASSWORD=<what the shop will actually use>
```

And set the WhatsApp number in `/admin` → Shop details. Country code first,
digits only: `919846000000`.

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Deploying

GitHub Pages will not work — this needs a Python process. Free options that will:

- **Render** — connect the repo, Build: `pip install -r requirements.txt`,
  Start: `gunicorn app:app`. Add the env vars in the dashboard.
- **Railway** or **Fly.io** — same shape, `Procfile` is already here.

One caveat on free tiers: the filesystem is usually wiped on redeploy, which
means `zain.db` and everything in it disappears. For a shop that matters. Either
pay for a persistent disk (Render, a few dollars a month) or attach a managed
Postgres and swap the `sqlite3` calls in `app.py` for it.

## Updating rates

The shop signs in at `/admin`, types the new numbers, hits **Save rates**. The
"Rates updated" line on the shop page changes by itself. No code, no deploy.
