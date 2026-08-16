"""
Zain Bazaar — storefront + rate manager.

Run locally:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000

Shop-facing rate editor lives at /admin
"""

import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, g)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ZAIN_DB", os.path.join(BASE, "zain.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-before-you-deploy")

# Password for the /admin rate editor. Set ADMIN_PASSWORD in the environment
# on the server — never leave the fallback in place once it's live.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "zain2026")

IST = timezone(timedelta(hours=5, minutes=30))
OPEN_HOUR, CLOSE_HOUR = 7, 23


# ---------------------------------------------------------------- database

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    en       TEXT    NOT NULL,
    ml       TEXT    NOT NULL DEFAULT '',
    unit     TEXT    NOT NULL DEFAULT '1 kg',
    price    REAL    NOT NULL,
    cat      TEXT    NOT NULL DEFAULT 'Provisions',
    active   INTEGER NOT NULL DEFAULT 1,
    sort     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    placed   TEXT NOT NULL,
    total    REAL NOT NULL,
    lines    TEXT NOT NULL
);
"""

SEED_ITEMS = [
    # en, ml, unit, price, cat
    ("Tomato",         "തക്കാളി",        "1 kg",   38,  "Vegetables"),
    ("Onion",          "സവാള",           "1 kg",   42,  "Vegetables"),
    ("Potato",         "ഉരുളക്കിഴങ്ങ്",    "1 kg",   36,  "Vegetables"),
    ("Carrot",         "കാരറ്റ്",          "1 kg",   64,  "Vegetables"),
    ("Green chilli",   "പച്ചമുളക്",        "250 g",  22,  "Vegetables"),
    ("Ginger",         "ഇഞ്ചി",           "250 g",  34,  "Vegetables"),
    ("Garlic",         "വെളുത്തുള്ളി",      "250 g",  48,  "Vegetables"),
    ("Curry leaves",   "കറിവേപ്പില",      "bunch",  10,  "Vegetables"),
    ("Nendran banana", "നേന്ത്രക്കായ",      "1 kg",   72,  "Fruits"),
    ("Robusta banana", "റോബസ്റ്റ പഴം",     "1 kg",   48,  "Fruits"),
    ("Apple",          "ആപ്പിൾ",          "1 kg",   180, "Fruits"),
    ("Orange",         "ഓറഞ്ച്",          "1 kg",   120, "Fruits"),
    ("Coconut",        "തേങ്ങ",           "1 pc",   42,  "Fruits"),
    ("Matta rice",     "മട്ട അരി",         "1 kg",   56,  "Provisions"),
    ("Jaya rice",      "ജയ അരി",          "1 kg",   52,  "Provisions"),
    ("Coconut oil",    "വെളിച്ചെണ്ണ",       "1 litre",290, "Provisions"),
    ("Toor dal",       "തുവരപ്പരിപ്പ്",     "1 kg",   145, "Provisions"),
    ("Sugar",          "പഞ്ചസാര",         "1 kg",   46,  "Provisions"),
    ("Jaggery",        "ശർക്കര",          "500 g",  60,  "Provisions"),
    ("Tea powder",     "ചായപ്പൊടി",       "500 g",  210, "Provisions"),
    ("Eggs",           "മുട്ട",            "dozen",  84,  "Provisions"),
]

DEFAULT_SETTINGS = {
    "wa_number": "910000000000",      # country code + number, digits only
    "rates_updated": "not set yet",
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    cur = conn.execute("SELECT COUNT(*) FROM items")
    if cur.fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO items (en, ml, unit, price, cat, sort) "
            "VALUES (?,?,?,?,?,?)",
            [(*row, i) for i, row in enumerate(SEED_ITEMS)],
        )
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    conn.commit()
    conn.close()


def get_setting(key, default=""):
    row = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    db().execute(
        "INSERT INTO settings (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    db().commit()


# ---------------------------------------------------------------- helpers

def shop_is_open():
    now = datetime.now(IST)
    return OPEN_HOUR <= now.hour < CLOSE_HOUR


def live_items(include_hidden=False):
    sql = "SELECT * FROM items"
    if not include_hidden:
        sql += " WHERE active=1"
    sql += " ORDER BY sort, id"
    return db().execute(sql).fetchall()


def admin_only(view):
    @wraps(view)
    def guard(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return guard


# ---------------------------------------------------------------- storefront

@app.route("/")
def index():
    rows = live_items()
    items = [dict(r) for r in rows]
    cats = []
    for it in items:
        if it["cat"] not in cats:
            cats.append(it["cat"])
    return render_template(
        "index.html",
        items=items,
        items_json=json.dumps(items, ensure_ascii=False),
        cats=cats,
        wa_number=get_setting("wa_number"),
        rates_updated=get_setting("rates_updated"),
        is_open=shop_is_open(),
    )


@app.post("/api/order")
def log_order():
    """Record the basket before the customer is handed to WhatsApp.

    This is what gives the shop a picture of demand — which items people
    ask for, and what they ask for that isn't stocked.
    """
    data = request.get_json(silent=True) or {}
    lines = data.get("lines") or []
    total = float(data.get("total") or 0)
    if not lines:
        return jsonify(ok=False, error="empty order"), 400
    db().execute(
        "INSERT INTO orders (placed, total, lines) VALUES (?,?,?)",
        (datetime.now(IST).isoformat(timespec="minutes"), total,
         json.dumps(lines, ensure_ascii=False)),
    )
    db().commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- admin

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(request.args.get("next") or url_for("admin"))
        flash("That password didn't match. Try again.")
    return render_template("login.html")


@app.get("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


@app.get("/admin")
@admin_only
def admin():
    orders = db().execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT 25").fetchall()
    parsed = [{"id": o["id"], "placed": o["placed"], "total": o["total"],
               "lines": json.loads(o["lines"])} for o in orders]
    return render_template(
        "admin.html",
        items=live_items(include_hidden=True),
        orders=parsed,
        wa_number=get_setting("wa_number"),
        rates_updated=get_setting("rates_updated"),
    )


@app.post("/admin/prices")
@admin_only
def save_prices():
    """Bulk-save every price and visibility toggle on the page."""
    changed = 0
    for row in live_items(include_hidden=True):
        price_raw = request.form.get(f"price_{row['id']}")
        if price_raw is None:
            continue
        try:
            price = round(float(price_raw), 2)
        except ValueError:
            continue
        active = 1 if request.form.get(f"active_{row['id']}") else 0
        if price != row["price"] or active != row["active"]:
            db().execute("UPDATE items SET price=?, active=? WHERE id=?",
                         (price, active, row["id"]))
            changed += 1
    db().commit()
    if changed:
        set_setting("rates_updated", datetime.now(IST).strftime("%-d %B %Y"))
    flash(f"Saved. {changed} item{'s' if changed != 1 else ''} updated."
          if changed else "Nothing changed.")
    return redirect(url_for("admin"))


@app.post("/admin/item")
@admin_only
def add_item():
    en = (request.form.get("en") or "").strip()
    if not en:
        flash("An item needs an English name.")
        return redirect(url_for("admin"))
    try:
        price = round(float(request.form.get("price") or 0), 2)
    except ValueError:
        price = 0
    top = db().execute("SELECT COALESCE(MAX(sort),0)+1 AS n FROM items").fetchone()["n"]
    db().execute(
        "INSERT INTO items (en, ml, unit, price, cat, sort) VALUES (?,?,?,?,?,?)",
        (en, (request.form.get("ml") or "").strip(),
         (request.form.get("unit") or "1 kg").strip(), price,
         (request.form.get("cat") or "Provisions").strip(), top),
    )
    db().commit()
    set_setting("rates_updated", datetime.now(IST).strftime("%-d %B %Y"))
    flash(f"Added {en}.")
    return redirect(url_for("admin"))


@app.post("/admin/item/<int:item_id>/delete")
@admin_only
def delete_item(item_id):
    db().execute("DELETE FROM items WHERE id=?", (item_id,))
    db().commit()
    flash("Item removed.")
    return redirect(url_for("admin"))


@app.post("/admin/settings")
@admin_only
def save_settings():
    digits = "".join(c for c in (request.form.get("wa_number") or "") if c.isdigit())
    if digits:
        set_setting("wa_number", digits)
    flash("Shop details saved.")
    return redirect(url_for("admin"))


# ---------------------------------------------------------------- entry

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
