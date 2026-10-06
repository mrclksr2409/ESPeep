// ESPeep sidebar panel: manage the barcode -> name table.
//
// Plain web component without a build step, so the integration ships as-is
// through HACS. Talks to the backend only through the espeep/* WebSocket
// commands in websocket.py.

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const fmtTime = (iso) => {
  if (!iso) return "–";
  const date = new Date(iso);
  return isNaN(date) ? "–" : date.toLocaleString();
};

// Same GS1 check the firmware and the backend do, so typos are caught while typing.
const validEan = (raw) => {
  const code = String(raw).replace(/\D/g, "");
  if (![8, 12, 13, 14].includes(code.length)) return null;
  let sum = 0;
  for (let i = 0; i < code.length - 1; i++) {
    const digit = Number(code[code.length - 2 - i]);
    sum += i % 2 === 0 ? digit * 3 : digit;
  }
  return (10 - (sum % 10)) % 10 === Number(code[code.length - 1]) ? code : null;
};

const RESULT_LABELS = {
  added: "Auf die Liste",
  already_listed: "Schon auf der Liste",
  recognised: "Erkannt",
  unknown: "Unbekannt",
  lookup_failed: "Keine Verbindung",
  list_failed: "Liste nicht erreichbar",
  invalid: "Ungültig",
};

const SOURCE_LABELS = { user: "eigener Name", online: "online" };

class EspeepPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = { products: {}, unknown: {}, history: [], scanners: [] };
    this._filter = "";
    this._editing = null;
    this._message = null;
    this._unsub = null;
    this._rendered = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._subscribe();
    if (!this._rendered) this._render();
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = hass;
      menu.narrow = this._narrow;
    }
  }

  set narrow(narrow) {
    this._narrow = narrow;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = narrow;
  }

  set panel(_panel) {}
  set route(_route) {}

  disconnectedCallback() {
    if (this._unsub) {
      this._unsub.then((unsub) => unsub()).catch(() => {});
      this._unsub = null;
    }
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
  }

  _subscribe() {
    this._unsub = this._hass.connection.subscribeMessage(
      (data) => {
        this._data = data;
        this._render();
      },
      { type: "espeep/subscribe" },
    );
  }

  async _ws(message) {
    try {
      return await this._hass.callWS(message);
    } catch (err) {
      this._flash(err.message || String(err), true);
      throw err;
    }
  }

  _flash(text, error = false) {
    this._message = { text, error };
    this._render();
    clearTimeout(this._flashTimer);
    this._flashTimer = setTimeout(() => {
      this._message = null;
      this._render();
    }, 5000);
  }

  // --- rendering ----------------------------------------------------------

  _render() {
    this._rendered = true;
    const root = this.shadowRoot;
    // Keep what the user is typing across re-renders triggered by updates.
    const focused = root.activeElement;
    const focusId = focused && focused.id;
    const values = {};
    root.querySelectorAll("input, textarea, select").forEach((el) => {
      if (el.id) values[el.id] = el.value;
    });

    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">ESPeep</div>
      </div>
      <div class="content">
        ${this._message ? `<div class="flash ${this._message.error ? "error" : ""}">${esc(this._message.text)}</div>` : ""}
        ${this._renderScanners()}
        ${this._renderUnknown()}
        ${this._renderAdd()}
        ${this._renderProducts()}
        ${this._renderHistory()}
        ${this._renderImport()}
      </div>`;

    const menu = root.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
    // Entering or leaving edit mode fills the form from the product instead.
    const resetForm = this._resetForm;
    this._resetForm = false;
    for (const [id, value] of Object.entries(values)) {
      const el = root.getElementById(id);
      if (el && !(resetForm && id.startsWith("f-"))) el.value = value;
    }
    if (focusId) {
      const el = root.getElementById(focusId);
      if (el) {
        el.focus();
        if (el.setSelectionRange && el.type !== "number") el.setSelectionRange(el.value.length, el.value.length);
      }
    }
    this._bind();
  }

  _renderScanners() {
    if (this._data.scanners.length) return "";
    return `<div class="card warn">
      Kein ESPeep-Scanner eingerichtet. Füge die Integration unter
      <i>Einstellungen → Geräte &amp; Dienste</i> hinzu, um Scans zu verarbeiten.
      Die Produktdatenbank kannst du trotzdem schon pflegen.
    </div>`;
  }

  _renderUnknown() {
    const entries = Object.entries(this._data.unknown).sort((a, b) =>
      b[1].last_seen.localeCompare(a[1].last_seen),
    );
    if (!entries.length) return "";
    const canList = this._data.scanners.length > 0;
    return `<div class="card">
      <h2>Unbekannte Barcodes <span class="badge">${entries.length}</span></h2>
      <p class="hint">Gescannt, aber in keiner Datenbank gefunden. Gib ihnen einen Namen –
      ab dann werden sie sofort erkannt.</p>
      ${entries
        .map(
          ([ean, info]) => `
        <div class="row unknown" data-ean="${esc(ean)}">
          <div class="ean">${esc(ean)}<small>${info.count}× gescannt, zuletzt ${esc(fmtTime(info.last_seen))}</small></div>
          <input id="unk-${esc(ean)}" placeholder="Name, z. B. Milch" />
          <div class="actions">
            ${canList ? `<button class="primary" data-action="learn">Speichern + auf Liste</button>` : ""}
            <button data-action="name-only">Nur speichern</button>
            <button data-action="lookup-unknown" title="Online nachschlagen">Nachschlagen</button>
            <button class="danger" data-action="dismiss" title="Verwerfen">✕</button>
          </div>
        </div>`,
        )
        .join("")}
    </div>`;
  }

  _renderAdd() {
    const editing = this._editing;
    const product = editing ? this._data.products[editing] : null;
    return `<div class="card">
      <h2>${editing ? "Produkt bearbeiten" : "Produkt anlegen"}</h2>
      <div class="form">
        <label>Barcode (EAN)
          <input id="f-ean" inputmode="numeric" value="${esc(editing || "")}" placeholder="4008400202037" />
        </label>
        <label>Name auf der Einkaufsliste
          <input id="f-name" value="${esc(product ? product.name : "")}" placeholder="Milch" />
        </label>
        <label>Marke (optional)
          <input id="f-brand" value="${esc(product ? product.brand : "")}" />
        </label>
        <label>Menge (optional)
          <input id="f-quantity" value="${esc(product ? product.quantity : "")}" />
        </label>
      </div>
      <div class="actions">
        <button class="primary" data-action="save">${editing ? "Änderungen speichern" : "Anlegen"}</button>
        <button data-action="lookup">Online nachschlagen</button>
        ${editing ? `<button data-action="cancel">Abbrechen</button>` : ""}
      </div>
    </div>`;
  }

  _renderProducts() {
    const filter = this._filter.toLowerCase();
    const entries = Object.entries(this._data.products)
      .filter(
        ([ean, p]) =>
          !filter ||
          ean.includes(filter) ||
          p.name.toLowerCase().includes(filter) ||
          (p.brand || "").toLowerCase().includes(filter),
      )
      .sort((a, b) => a[1].name.localeCompare(b[1].name));
    const total = Object.keys(this._data.products).length;
    const canList = this._data.scanners.length > 0;

    return `<div class="card">
      <h2>Produkte <span class="badge">${total}</span></h2>
      <input id="filter" class="filter" placeholder="Suchen nach Name, Marke oder Barcode" value="${esc(this._filter)}" />
      ${
        entries.length
          ? `<table>
        <thead><tr><th>Name</th><th>Barcode</th><th class="wide">Marke / Menge</th><th class="wide">Herkunft</th><th class="wide">Scans</th><th></th></tr></thead>
        <tbody>
        ${entries
          .map(
            ([ean, p]) => `<tr data-ean="${esc(ean)}">
            <td><b>${esc(p.name)}</b></td>
            <td class="mono">${esc(ean)}</td>
            <td class="wide">${esc([p.brand, p.quantity].filter(Boolean).join(" · ") || "–")}</td>
            <td class="wide"><span class="tag ${esc(p.source)}">${esc(SOURCE_LABELS[p.source] || p.source)}</span></td>
            <td class="wide">${p.scans || 0}</td>
            <td><div class="row-actions">
              ${canList ? `<button data-action="list" title="Auf die Einkaufsliste">🛒</button>` : ""}
              <button data-action="edit" title="Bearbeiten">✎</button>
              <button class="danger" data-action="delete" title="Löschen">✕</button>
            </div></td>
          </tr>`,
          )
          .join("")}
        </tbody></table>`
          : `<p class="hint">${total ? "Keine Treffer." : "Noch keine Produkte. Scanne etwas oder lege oben eins an."}</p>`
      }
    </div>`;
  }

  _renderHistory() {
    if (!this._data.history.length) return "";
    return `<div class="card">
      <h2>Letzte Scans</h2>
      <table>
        <thead><tr><th>Zeit</th><th>Produkt</th><th>Ergebnis</th><th class="wide">Scanner</th></tr></thead>
        <tbody>
        ${this._data.history
          .slice(0, 20)
          .map(
            (h) => `<tr>
            <td>${esc(fmtTime(h.time))}</td>
            <td>${esc(h.name || h.ean)}${h.name ? `<small class="mono"> ${esc(h.ean)}</small>` : ""}</td>
            <td><span class="tag r-${esc(h.result)}">${esc(RESULT_LABELS[h.result] || h.result)}</span></td>
            <td class="wide">${esc(h.device)}</td>
          </tr>`,
          )
          .join("")}
        </tbody>
      </table>
    </div>`;
  }

  _renderImport() {
    return `<details class="card" ${this._importOpen ? "open" : ""}>
      <summary><h2>Import / Export</h2></summary>
      <p class="hint">Eine Zeile pro Produkt, Barcode und Name getrennt durch
      <code>;</code>, <code>,</code>, Tab oder <code>:</code>. Das Format der
      alten <code>ean_mapping.yaml</code> (<code>"4008400202037": "Milch"</code>)
      funktioniert direkt.</p>
      <textarea id="import-text" rows="6" placeholder='"4008400202037": "Milch"&#10;4104420045200;Spülmaschinentabs'></textarea>
      <div class="actions">
        <button class="primary" data-action="import">Importieren</button>
        <button data-action="export-csv">Als CSV exportieren</button>
        <button data-action="export-json">Als JSON exportieren</button>
      </div>
    </details>`;
  }

  // --- events -------------------------------------------------------------

  _bind() {
    const root = this.shadowRoot;
    const details = root.querySelector("details");
    details.addEventListener("toggle", () => (this._importOpen = details.open));
    const filter = root.getElementById("filter");
    filter.addEventListener("input", () => {
      this._filter = filter.value;
      this._render();
    });

    root.querySelectorAll("button[data-action]").forEach((button) =>
      button.addEventListener("click", (ev) => this._onAction(ev, button.dataset.action)),
    );
    root.querySelectorAll(".row.unknown input").forEach((input) =>
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          const canList = this._data.scanners.length > 0;
          this._onAction(ev, canList ? "learn" : "name-only");
        }
      }),
    );
    ["f-ean", "f-name", "f-brand", "f-quantity"].forEach((id) =>
      root.getElementById(id).addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") this._onAction(ev, "save");
      }),
    );
  }

  async _onAction(ev, action) {
    const root = this.shadowRoot;
    const row = ev.target.closest("[data-ean]");
    const ean = row && row.dataset.ean;

    switch (action) {
      case "learn":
      case "name-only": {
        const name = root.getElementById(`unk-${ean}`).value.trim();
        if (!name) return this._flash("Bitte einen Namen eingeben.", true);
        if (action === "learn") {
          const result = await this._ws({ type: "espeep/learn", ean, name });
          this._flash(`„${result.name}“: ${RESULT_LABELS[result.result] || result.result}`);
        } else {
          await this._ws({ type: "espeep/set", ean, name });
          this._flash(`„${name}“ gespeichert.`);
        }
        break;
      }
      case "lookup-unknown": {
        const result = await this._ws({ type: "espeep/lookup", ean });
        if (result.product) {
          root.getElementById(`unk-${ean}`).value = result.product.name;
          this._flash(`Gefunden in ${result.product.database}: ${result.product.name}`);
        } else {
          this._flash("Auch online nicht gefunden.", true);
        }
        break;
      }
      case "dismiss":
        await this._ws({ type: "espeep/dismiss", ean });
        break;
      case "save": {
        const value = (id) => root.getElementById(id).value.trim();
        const code = validEan(value("f-ean"));
        if (!code) return this._flash("Kein gültiger Barcode (Länge oder Prüfziffer).", true);
        if (!value("f-name")) return this._flash("Bitte einen Namen eingeben.", true);
        if (!this._editing && this._data.products[code]) {
          if (!confirm(`${code} ist schon als „${this._data.products[code].name}“ gespeichert. Überschreiben?`))
            return;
        }
        const message = {
          type: "espeep/set",
          ean: code,
          name: value("f-name"),
          brand: value("f-brand"),
          quantity: value("f-quantity"),
        };
        if (this._editing) message.previous_ean = this._editing;
        await this._ws(message);
        this._editing = null;
        this._resetForm = true;
        ["f-ean", "f-name", "f-brand", "f-quantity"].forEach((id) => (root.getElementById(id).value = ""));
        this._flash(`„${message.name}“ gespeichert.`);
        break;
      }
      case "lookup": {
        const code = validEan(root.getElementById("f-ean").value);
        if (!code) return this._flash("Kein gültiger Barcode (Länge oder Prüfziffer).", true);
        const result = await this._ws({ type: "espeep/lookup", ean: code });
        if (!result.product) return this._flash("Online nicht gefunden.", true);
        const { name, brand, quantity, database } = result.product;
        if (!root.getElementById("f-name").value) root.getElementById("f-name").value = name;
        root.getElementById("f-brand").value = brand;
        root.getElementById("f-quantity").value = quantity;
        this._flash(`Gefunden in ${database}: ${[brand, name].filter(Boolean).join(" ")}`);
        break;
      }
      case "cancel":
        this._editing = null;
        this._resetForm = true;
        this._render();
        break;
      case "edit":
        this._editing = ean;
        this._resetForm = true;
        this._render();
        root.getElementById("f-name").focus();
        root.querySelector(".card h2").scrollIntoView({ behavior: "smooth" });
        break;
      case "delete": {
        const product = this._data.products[ean];
        if (!confirm(`„${product.name}“ (${ean}) löschen?`)) return;
        await this._ws({ type: "espeep/delete", ean });
        if (this._editing === ean) this._editing = null;
        break;
      }
      case "list": {
        const result = await this._ws({ type: "espeep/add_to_list", ean });
        this._flash(`„${result.name}“: ${RESULT_LABELS[result.result] || result.result}`);
        break;
      }
      case "import":
        await this._import();
        break;
      case "export-csv": {
        const lines = Object.entries(this._data.products).map(
          ([code, p]) => [code, p.name, p.brand, p.quantity].map((v) => `"${String(v || "").replace(/"/g, '""')}"`).join(";"),
        );
        this._download("espeep-produkte.csv", ["ean;name;brand;quantity", ...lines].join("\n"), "text/csv");
        break;
      }
      case "export-json":
        this._download("espeep-produkte.json", JSON.stringify(this._data.products, null, 2), "application/json");
        break;
    }
  }

  async _import() {
    const text = this.shadowRoot.getElementById("import-text").value;
    const products = {};
    let skipped = 0;
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("#") || /^ean[;,\t]/i.test(line)) continue;
      const match = line.match(/^["']?(\d{8,14})["']?\s*[;,:\t]\s*(.+)$/);
      if (!match) {
        skipped++;
        continue;
      }
      // Strip YAML/CSV quoting and a trailing CSV brand/quantity.
      let name = match[2].trim();
      const quoted = name.match(/^"((?:[^"]|"")*)"/) || name.match(/^'([^']*)'/);
      name = quoted ? quoted[1].replace(/""/g, '"') : name.split(/[;\t]/)[0];
      products[match[1]] = name.trim();
    }
    if (!Object.keys(products).length) return this._flash("Nichts zum Importieren gefunden.", true);
    const result = await this._ws({ type: "espeep/import", products });
    const rejected = result.rejected.length + skipped;
    this.shadowRoot.getElementById("import-text").value = "";
    this._flash(
      `${result.imported} Produkte importiert` +
        (rejected ? `, ${rejected} Zeilen übersprungen (ungültiger Barcode oder Format).` : "."),
      rejected > 0,
    );
  }

  _download(filename, content, type) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  .toolbar {
    display: flex; align-items: center; height: 56px; padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    position: sticky; top: 0; z-index: 2;
  }
  .title { font-size: 20px; margin-left: 12px; }
  .content { max-width: 1000px; margin: 0 auto; padding: 16px; }
  .card {
    background: var(--card-background-color, #fff);
    border-radius: var(--ha-card-border-radius, 12px);
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.2));
    border: var(--ha-card-border-width, 0) solid var(--ha-card-border-color, transparent);
    padding: 16px; margin-bottom: 16px;
  }
  .card.warn { border-left: 4px solid var(--warning-color, #ff9800); }
  h2 { font-size: 18px; font-weight: 500; margin: 0 0 12px; display: inline-flex; gap: 8px; align-items: center; }
  summary { cursor: pointer; list-style: none; }
  summary h2 { margin: 0; }
  details[open] summary { margin-bottom: 12px; }
  .badge {
    background: var(--primary-color); color: var(--text-primary-color, #fff);
    border-radius: 10px; padding: 0 8px; font-size: 13px; line-height: 20px;
  }
  .hint { color: var(--secondary-text-color); margin: 0 0 12px; font-size: 14px; }
  input, textarea {
    font: inherit; color: var(--primary-text-color);
    background: var(--input-fill-color, var(--secondary-background-color));
    border: 1px solid var(--divider-color); border-radius: 6px;
    padding: 8px 10px; box-sizing: border-box; width: 100%;
  }
  input:focus, textarea:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; }
  .form { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  button {
    font: inherit; font-size: 14px; cursor: pointer;
    border: 1px solid var(--divider-color); border-radius: 6px;
    background: transparent; color: var(--primary-color); padding: 6px 12px;
  }
  button:hover { background: var(--secondary-background-color); }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  button.danger { color: var(--error-color, #db4437); }
  .filter { margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th { text-align: left; color: var(--secondary-text-color); font-weight: 500; padding: 6px 8px; border-bottom: 1px solid var(--divider-color); }
  td { padding: 6px 8px; border-bottom: 1px solid var(--divider-color); vertical-align: middle; }
  .row-actions { display: flex; gap: 4px; justify-content: flex-end; }
  .row-actions button { padding: 4px 8px; }
  .mono { font-family: var(--code-font-family, monospace); }
  small { display: block; color: var(--secondary-text-color); font-size: 12px; }
  td small { display: inline; }
  .tag { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: var(--secondary-background-color); white-space: nowrap; }
  .tag.user, .tag.r-added { background: rgba(76,175,80,.2); }
  .tag.online { background: rgba(33,150,243,.2); }
  .tag.r-unknown, .tag.r-lookup_failed, .tag.r-list_failed, .tag.r-invalid { background: rgba(244,67,54,.2); }
  .row.unknown { display: grid; grid-template-columns: 200px 1fr; gap: 8px 12px; align-items: center; padding: 10px 0; border-top: 1px solid var(--divider-color); }
  .row.unknown .actions { grid-column: 1 / -1; margin-top: 0; }
  .ean { font-family: var(--code-font-family, monospace); font-size: 15px; }
  .flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; background: rgba(76,175,80,.2); }
  .flash.error { background: rgba(244,67,54,.2); }
  code { font-family: var(--code-font-family, monospace); }
  @media (max-width: 700px) {
    .wide { display: none; }
    .row.unknown { grid-template-columns: 1fr; }
  }
`;

if (!customElements.get("espeep-panel")) customElements.define("espeep-panel", EspeepPanel);
