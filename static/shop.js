/* Zain Bazaar storefront — rates board, order sheet, WhatsApp handoff.
   ITEMS and WA_NUMBER are injected by the server in index.html. */

const OPEN_H = 7, CLOSE_H = 23;
const cart = new Map();
let filter = "All";

const rowsEl  = document.getElementById("rows");
const sheet   = document.getElementById("sheet");

/* ---------- open / closed, computed in Kannur time ---------- */
function kannurNow() {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata", weekday: "long",
    hour: "2-digit", minute: "2-digit", hour12: false
  }).formatToParts(new Date());
  const g = t => parts.find(p => p.type === t).value;
  return { day: g("weekday"), h: +g("hour"), m: +g("minute") };
}

function paintStatus() {
  const n = kannurNow(), open = n.h >= OPEN_H && n.h < CLOSE_H;
  const dot = document.getElementById("statusDot");
  const txt = document.getElementById("statusText");
  dot.classList.toggle("dot--shut", !open);
  if (open) {
    const left = (CLOSE_H - n.h - 1) * 60 + (60 - n.m);
    txt.textContent = left <= 60 ? "Open · closing soon" : "Open now · until 11 PM";
  } else {
    txt.textContent = "Closed · opens 7 AM";
  }
  document.querySelectorAll("#hoursTable tr").forEach(tr => {
    tr.toggleAttribute("data-today", tr.dataset.day === n.day);
  });
}

/* ---------- hours table ---------- */
(function hours() {
  const days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
  document.getElementById("hoursTable").innerHTML =
    days.map(d => `<tr data-day="${d}"><td>${d}</td><td>7:00 – 23:00</td></tr>`).join("");
})();

/* ---------- rates board ---------- */
function drawRows() {
  rowsEl.innerHTML = ITEMS
    .map((it, i) => ({ ...it, i }))
    .filter(it => filter === "All" || it.cat === filter)
    .map(it => `
      <div class="row">
        <div class="row__names">
          <div class="row__en">${it.en}</div>
          <div class="row__ml">${it.ml}</div>
        </div>
        <div class="row__price">₹${it.price}<small>per ${it.unit}</small></div>
        <button class="add" data-i="${it.i}" data-in="${cart.has(it.i) ? 1 : 0}"
                aria-label="Add ${it.en} to order">${cart.has(it.i) ? "×" + cart.get(it.i) : "+"}</button>
      </div>`).join("");
}

document.getElementById("filters").addEventListener("click", e => {
  const b = e.target.closest(".chip");
  if (!b) return;
  filter = b.dataset.cat;
  document.querySelectorAll(".chip").forEach(c => c.setAttribute("aria-pressed", c === b));
  document.getElementById("ledgerLabel").textContent = filter === "All" ? "All items" : filter;
  drawRows();
});

rowsEl.addEventListener("click", e => {
  const b = e.target.closest(".add");
  if (!b) return;
  const i = +b.dataset.i;
  cart.set(i, (cart.get(i) || 0) + 1);
  drawRows(); sync();
});

/* ---------- order sheet ---------- */
function orderLines() {
  return [...cart].map(([i, q]) => ({
    en: ITEMS[i].en, ml: ITEMS[i].ml, unit: ITEMS[i].unit,
    qty: q, price: ITEMS[i].price
  }));
}

function orderTotal() {
  return [...cart].reduce((s, [i, q]) => s + ITEMS[i].price * q, 0);
}

function sync() {
  const n = [...cart.values()].reduce((a, b) => a + b, 0);
  document.getElementById("cartbar").dataset.show = n ? "1" : "0";
  document.getElementById("cartCount").textContent =
    n === 1 ? "1 item added" : n + " items added";

  const total = orderTotal();
  document.getElementById("total").textContent = "₹" + total;

  document.getElementById("sheetList").innerHTML = cart.size
    ? [...cart].map(([i, q]) => `
        <div class="line">
          <div>
            <div class="row__en">${ITEMS[i].en}</div>
            <div class="row__ml">${ITEMS[i].ml} · ₹${ITEMS[i].price} / ${ITEMS[i].unit}</div>
          </div>
          <div class="qty">
            <button data-d="-1" data-i="${i}" aria-label="Fewer ${ITEMS[i].en}">−</button>
            <span>${q} × ${ITEMS[i].unit}</span>
            <button data-d="1" data-i="${i}" aria-label="More ${ITEMS[i].en}">+</button>
          </div>
        </div>`).join("")
    : `<p class="note" style="padding:26px 0">Nothing added yet. Tap items on the rates board to build your list.</p>`;

  const lines = [...cart].map(([i, q], k) =>
    `${k + 1}. ${ITEMS[i].en} (${ITEMS[i].ml}) — ${q} × ${ITEMS[i].unit}`);
  const msg =
`*Zain Bazaar — home delivery order*

${lines.join("\n")}

Estimated total: ₹${total}

Name:
Address:
Preferred delivery time:`;
  document.getElementById("waSend").href =
    "https://wa.me/" + WA_NUMBER + "?text=" + encodeURIComponent(msg);
}

document.getElementById("sheetList").addEventListener("click", e => {
  const b = e.target.closest("button[data-d]");
  if (!b) return;
  const i = +b.dataset.i, q = (cart.get(i) || 0) + (+b.dataset.d);
  q > 0 ? cart.set(i, q) : cart.delete(i);
  drawRows(); sync();
});

document.getElementById("openSheet").onclick = () => {
  sheet.dataset.open = "1";
  document.getElementById("closeSheet").focus();
};
document.getElementById("closeSheet").onclick = () => sheet.dataset.open = "0";
sheet.addEventListener("click", e => { if (e.target === sheet) sheet.dataset.open = "0"; });
document.addEventListener("keydown", e => { if (e.key === "Escape") sheet.dataset.open = "0"; });

/* Record the basket on the way out, so the shop can see what people ask for.
   Never blocks the WhatsApp handoff — if the log fails, the order still sends. */
document.getElementById("waSend").addEventListener("click", () => {
  if (!cart.size) return;
  const payload = JSON.stringify({ lines: orderLines(), total: orderTotal() });
  if (navigator.sendBeacon) {
    navigator.sendBeacon("/api/order", new Blob([payload], { type: "application/json" }));
  } else {
    fetch("/api/order", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: payload, keepalive: true
    }).catch(() => {});
  }
});

drawRows(); sync(); paintStatus();
setInterval(paintStatus, 60000);
