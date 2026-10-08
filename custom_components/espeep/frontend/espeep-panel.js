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

// ZXing is only needed where the browser has no BarcodeDetector, so it is
// loaded on first use from the vendor folder next to this file.
let zxingPromise = null;
const loadZXing = () => {
  if (window.ZXing) return Promise.resolve(window.ZXing);
  zxingPromise ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = new URL("vendor/zxing.min.js", import.meta.url).href;
    script.onload = () => (window.ZXing ? resolve(window.ZXing) : reject(new Error("ZXing nicht geladen")));
    script.onerror = () => {
      zxingPromise = null;
      reject(new Error("ZXing konnte nicht geladen werden"));
    };
    document.head.appendChild(script);
  });
  return zxingPromise;
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
    this._closeScan();
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
    const focusId = focused && focused.closest("#page") && focused.id;
    const values = {};
    root.querySelectorAll("#page input, #page textarea, #page select").forEach((el) => {
      if (el.id) values[el.id] = el.value;
    });

    // The scan overlay lives next to the page, not in it: database updates
    // re-render the page and must not tear down the running camera.
    if (!this._page) {
      root.innerHTML = `<style>${STYLE}</style><div id="page"></div><div id="scan-layer"></div>`;
      this._page = root.getElementById("page");
    }
    const canScan = this._data.scanners.length > 0;
    this._page.innerHTML = `
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">ESPeep</div>
        ${canScan ? `<button class="scan-button" data-action="scan" title="Barcode mit der Kamera scannen">📷 Scannen</button>` : ""}
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

    this._page.querySelectorAll("button[data-action]").forEach((button) =>
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
      case "scan":
        this._openScan();
        break;
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

  // --- phone scanner ------------------------------------------------------
  //
  // A scan from the phone is handled exactly like one from the device:
  // espeep/add_to_list runs the same lookup chain, puts the product on the
  // list and shows it on the chosen ESPeep's display. Unknown barcodes are
  // named right here in the overlay.
  //
  // Decoders, best first: the Companion app's own scanner, the browser's
  // BarcodeDetector, and the bundled ZXing for everything else (iOS, Firefox).

  _openScan() {
    if (this._scan) return;
    const scanners = this._data.scanners;
    this._scan = {
      entryId: scanners.some((s) => s.entry_id === this._scanEntry) ? this._scanEntry : scanners[0].entry_id,
      results: [],
      lastCode: null,
      lastAt: 0,
      busy: false,
    };
    if (this._externalBus()) this._startNative();
    else this._startCamera();
  }

  _closeScan() {
    const scan = this._scan;
    if (!scan) return;
    this._scan = null;
    clearTimeout(scan.timer);
    clearTimeout(scan.resumeTimer);
    if (scan.stream) scan.stream.getTracks().forEach((track) => track.stop());
    this._stopNative(scan, true);
    const layer = this.shadowRoot.getElementById("scan-layer");
    if (layer) layer.innerHTML = "";
  }

  // Only while our scan runs, barcode results from the app come to us. The
  // frontend keeps its own listeners for them private, so we sit in front of
  // its message handler and pass everything else through untouched.
  _externalBus() {
    const bus = this._hass.auth && this._hass.auth.external;
    return bus && bus.config && bus.config.hasBarCodeScanner && typeof bus.receiveMessage === "function"
      ? bus
      : null;
  }

  _startNative() {
    const bus = this._externalBus();
    const scan = this._scan;
    if (!bus || !scan || scan.native) return;
    const hadOwn = Object.prototype.hasOwnProperty.call(bus, "receiveMessage");
    const original = bus.receiveMessage;
    bus.receiveMessage = (msg) => {
      if (msg && msg.type === "command" && String(msg.command).startsWith("bar_code/")) {
        bus.fireMessage({ id: msg.id, type: "result", success: true, result: null });
        this._onNativeMessage(msg);
        return;
      }
      return original.call(bus, msg);
    };
    scan.native = {
      bus,
      restore: () => (hadOwn ? (bus.receiveMessage = original) : delete bus.receiveMessage),
    };
    bus.fireMessage({
      type: "bar_code/scan",
      payload: {
        title: "ESPeep",
        description: "Barcode eines Produkts scannen – er landet direkt auf der Einkaufsliste.",
        alternative_option_label: "Kamera im Browser",
      },
    });
    this._renderScanLayer();
  }

  _stopNative(scan, closeApp) {
    if (!scan || !scan.native) return;
    if (closeApp) scan.native.bus.fireMessage({ type: "bar_code/close" });
    scan.native.restore();
    scan.native = null;
  }

  async _onNativeMessage(msg) {
    const scan = this._scan;
    if (!scan) return;
    if (msg.command === "bar_code/aborted") {
      this._stopNative(scan, false);
      if (msg.payload && msg.payload.reason === "alternative_options") {
        this._startCamera();
      } else if (!scan.naming) {
        this._closeScan();
      } else {
        this._renderScanLayer();
      }
      return;
    }
    if (msg.command !== "bar_code/scan_result") return;
    const code = validEan((msg.payload && msg.payload.rawValue) || "");
    const notify = (message) => scan.native && scan.native.bus.fireMessage({ type: "bar_code/notify", payload: { message } });
    if (!code) return notify("Kein EAN-Barcode erkannt.");
    const result = await this._submitScan(code);
    if (!result || !this._scan) return;
    if (result.result === "unknown") {
      // Naming needs a keyboard: leave the app scanner, ask here.
      this._stopNative(scan, true);
      this._renderScanLayer();
    } else {
      notify(this._resultText(result));
    }
  }

  async _startCamera() {
    const scan = this._scan;
    scan.camera = true;
    this._renderScanLayer();
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return this._scanError(
        "Die Kamera ist nur über HTTPS erreichbar. Öffne Home Assistant über HTTPS " +
          "(z. B. Nabu Casa) oder nutze die Home-Assistant-App.",
      );
    }
    try {
      scan.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
    } catch (err) {
      return this._scanError(`Kein Zugriff auf die Kamera: ${err.message || err.name || err}`);
    }
    if (this._scan !== scan) return scan.stream.getTracks().forEach((track) => track.stop());
    const video = this.shadowRoot.getElementById("scan-video");
    video.srcObject = scan.stream;
    try {
      await video.play();
    } catch (_err) {
      // Autoplay of a muted inline video is allowed; play() can still reject
      // when the overlay was closed meanwhile.
    }
    const track = scan.stream.getVideoTracks()[0];
    const caps = track && track.getCapabilities ? track.getCapabilities() : {};
    scan.torchTrack = caps.torch ? track : null;
    try {
      scan.decode = await this._makeDecoder();
    } catch (err) {
      return this._scanError(`Barcode-Erkennung nicht verfügbar: ${err.message || err}`);
    }
    if (this._scan !== scan) return;
    this._renderScanLayer();
    this._scanLoop();
  }

  async _makeDecoder() {
    if ("BarcodeDetector" in window) {
      const supported = await window.BarcodeDetector.getSupportedFormats().catch(() => []);
      const formats = ["ean_13", "ean_8", "upc_a", "upc_e"].filter((f) => supported.includes(f));
      if (formats.length) {
        const detector = new window.BarcodeDetector({ formats });
        return async (video) => {
          const codes = await detector.detect(video);
          return codes.length ? codes[0].rawValue : null;
        };
      }
    }
    const ZXing = await loadZXing();
    const hints = new Map();
    hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
      ZXing.BarcodeFormat.EAN_13,
      ZXing.BarcodeFormat.EAN_8,
      ZXing.BarcodeFormat.UPC_A,
      ZXing.BarcodeFormat.UPC_E,
    ]);
    hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
    const reader = new ZXing.MultiFormatReader();
    reader.setHints(hints);
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { willReadFrequently: true });
    return async (video) => {
      if (!video.videoWidth) return null;
      // A centred band is enough for a 1D barcode and keeps the work small.
      const width = Math.min(video.videoWidth, 960);
      const scale = width / video.videoWidth;
      const band = Math.round(video.videoHeight * 0.5);
      canvas.width = width;
      canvas.height = Math.round(band * scale);
      context.drawImage(video, 0, (video.videoHeight - band) / 2, video.videoWidth, band, 0, 0, canvas.width, canvas.height);
      try {
        const bitmap = new ZXing.BinaryBitmap(
          new ZXing.HybridBinarizer(new ZXing.HTMLCanvasElementLuminanceSource(canvas)),
        );
        return reader.decodeWithState(bitmap).getText();
      } catch (_err) {
        return null; // nothing found in this frame
      }
    };
  }

  async _scanLoop() {
    const scan = this._scan;
    if (!scan || !scan.decode) return;
    if (!scan.busy && !scan.naming) {
      const video = this.shadowRoot.getElementById("scan-video");
      let raw = null;
      try {
        raw = video && video.readyState >= 2 ? await scan.decode(video) : null;
      } catch (_err) {
        raw = null;
      }
      const code = raw && validEan(raw);
      if (code && this._scan === scan) await this._submitScan(code);
    }
    if (this._scan === scan) scan.timer = setTimeout(() => this._scanLoop(), 150);
  }

  async _submitScan(code) {
    const scan = this._scan;
    const now = Date.now();
    // The same product stays in view for a while: one scan, not ten.
    if (scan.busy || (code === scan.lastCode && now - scan.lastAt < 4000)) return null;
    scan.busy = true;
    scan.lastCode = code;
    scan.lastAt = now;
    scan.error = null;
    if (navigator.vibrate) navigator.vibrate(80);
    scan.pending = code;
    this._renderScanLayer();
    let result;
    try {
      result = await this._hass.callWS({ type: "espeep/add_to_list", ean: code, entry_id: scan.entryId });
    } catch (err) {
      result = null;
      scan.error = err.message || String(err);
    }
    scan.pending = null;
    scan.busy = false;
    if (this._scan !== scan) return null;
    if (result) {
      scan.results.unshift(result);
      scan.results.length = Math.min(scan.results.length, 5);
      if (result.result === "unknown") scan.naming = result.ean;
    }
    this._renderScanLayer();
    if (scan.naming) this.shadowRoot.getElementById("scan-name").focus();
    return result;
  }

  async _learnScanned() {
    const scan = this._scan;
    const input = this.shadowRoot.getElementById("scan-name");
    const name = input.value.trim();
    if (!name) return input.focus();
    try {
      const result = await this._hass.callWS({ type: "espeep/learn", ean: scan.naming, name, entry_id: scan.entryId });
      scan.results[0] = result;
      scan.naming = null;
      scan.error = null;
    } catch (err) {
      scan.error = err.message || String(err);
    }
    this._afterNaming();
  }

  _afterNaming() {
    const scan = this._scan;
    if (!scan) return;
    // Back to where the scan came from: the app scanner or the camera.
    if (!scan.naming && !scan.camera && this._externalBus()) this._startNative();
    else this._renderScanLayer();
  }

  _scanError(text) {
    if (!this._scan) return;
    this._scan.error = text;
    this._scan.fatal = true;
    this._renderScanLayer();
  }

  _resultText(result) {
    return `${result.name ? `„${result.name}“` : result.ean}: ${RESULT_LABELS[result.result] || result.result}`;
  }

  _renderScanLayer() {
    const layer = this.shadowRoot.getElementById("scan-layer");
    const scan = this._scan;
    if (!scan) return (layer.innerHTML = "");
    const scanners = this._data.scanners;

    if (!layer.firstElementChild) {
      layer.innerHTML = `<div class="scan-overlay">
        <div class="scan-top">
          <div class="scan-title">Barcode scannen</div>
          <button id="scan-torch" class="scan-icon" title="Licht" hidden>🔦</button>
          <button id="scan-close" class="scan-icon" title="Schließen">✕</button>
        </div>
        <div class="scan-view" hidden>
          <video id="scan-video" playsinline muted autoplay></video>
          <div class="scan-frame"></div>
        </div>
        <div class="scan-panel"></div>
      </div>`;
      layer.querySelector("#scan-close").addEventListener("click", () => this._closeScan());
      layer.querySelector("#scan-torch").addEventListener("click", () => {
        const track = this._scan && this._scan.torchTrack;
        if (!track) return;
        this._scan.torch = !this._scan.torch;
        track.applyConstraints({ advanced: [{ torch: this._scan.torch }] }).catch(() => {});
      });
    }
    layer.querySelector(".scan-view").hidden = !scan.camera || scan.fatal;
    layer.querySelector("#scan-torch").hidden = !scan.torchTrack;

    const latest = scan.results[0];
    let status;
    if (scan.error) {
      status = `<div class="scan-status error">${esc(scan.error)}</div>`;
    } else if (scan.pending) {
      status = `<div class="scan-status">${esc(scan.pending)} …</div>`;
    } else if (scan.naming) {
      status = `<div class="scan-status warn">
        <b class="mono">${esc(scan.naming)}</b> kennt keine Datenbank. Wie soll er auf der Liste heißen?
        <input id="scan-name" placeholder="Name, z. B. Milch" />
        <div class="actions">
          <button class="primary" id="scan-learn">Speichern + auf Liste</button>
          <button id="scan-skip">Später</button>
        </div>
      </div>`;
    } else if (latest) {
      status = `<div class="scan-status ${latest.result === "added" ? "ok" : ""}">${esc(this._resultText(latest))}</div>`;
    } else if (scan.native) {
      status = `<div class="scan-status">Der Scanner der Home-Assistant-App ist geöffnet.</div>`;
    } else {
      status = `<div class="scan-status">${scan.decode ? "Barcode in den Rahmen halten." : "Kamera wird gestartet …"}</div>`;
    }

    const typing = this.shadowRoot.activeElement && this.shadowRoot.activeElement.id === "scan-name";
    const typed = typing ? this.shadowRoot.getElementById("scan-name").value : null;
    layer.querySelector(".scan-panel").innerHTML = `
      ${
        scanners.length > 1
          ? `<label>ESPeep (Einkaufsliste und Display)
          <select id="scan-entry">${scanners
            .map((s) => `<option value="${esc(s.entry_id)}" ${s.entry_id === scan.entryId ? "selected" : ""}>${esc(s.name)}</option>`)
            .join("")}</select></label>`
          : ""
      }
      ${status}
      ${
        scan.results.length > (scan.naming ? 0 : 1)
          ? `<ul class="scan-log">${scan.results
              .slice(scan.naming ? 0 : 1)
              .map((r) => `<li><span class="tag r-${esc(r.result)}">${esc(RESULT_LABELS[r.result] || r.result)}</span> ${esc(r.name || r.ean)}</li>`)
              .join("")}</ul>`
          : ""
      }
      ${!scan.camera && !scan.native && !scan.naming ? `<div class="actions"><button id="scan-again" class="primary">Weiter scannen</button></div>` : ""}`;

    const panel = layer.querySelector(".scan-panel");
    const select = panel.querySelector("#scan-entry");
    if (select)
      select.addEventListener("change", () => {
        scan.entryId = this._scanEntry = select.value;
      });
    const nameInput = panel.querySelector("#scan-name");
    if (nameInput) {
      if (typed !== null) {
        nameInput.value = typed;
        nameInput.focus();
      }
      nameInput.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") this._learnScanned();
      });
      panel.querySelector("#scan-learn").addEventListener("click", () => this._learnScanned());
      panel.querySelector("#scan-skip").addEventListener("click", () => {
        // It stays under "Unbekannte Barcodes" and in the notification.
        scan.naming = null;
        this._afterNaming();
      });
    }
    const again = panel.querySelector("#scan-again");
    if (again) again.addEventListener("click", () => this._startNative());
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
  .toolbar .scan-button {
    margin-left: auto; color: inherit; border-color: currentColor;
    background: rgba(255,255,255,.12); padding: 6px 14px;
  }
  .scan-overlay {
    position: fixed; inset: 0; z-index: 10; display: flex; flex-direction: column;
    background: var(--primary-background-color);
  }
  .scan-top {
    display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
  }
  .scan-title { font-size: 20px; flex: 1; }
  .scan-icon { color: inherit; border: none; font-size: 20px; padding: 6px 10px; }
  .scan-icon[hidden] { display: none; }
  .scan-view { position: relative; flex: 1; min-height: 0; background: #000; overflow: hidden; }
  .scan-view[hidden] { display: none; }
  .scan-view video { width: 100%; height: 100%; object-fit: cover; display: block; }
  .scan-frame {
    position: absolute; left: 10%; right: 10%; top: 35%; bottom: 35%;
    border: 3px solid rgba(255,255,255,.85); border-radius: 12px;
    box-shadow: 0 0 0 100vmax rgba(0,0,0,.35);
  }
  .scan-panel {
    padding: 16px; display: flex; flex-direction: column; gap: 12px;
    max-height: 50vh; overflow-y: auto; background: var(--card-background-color, #fff);
  }
  .scan-overlay .scan-view[hidden] + .scan-panel { flex: 1; max-height: none; }
  .scan-panel select {
    font: inherit; color: var(--primary-text-color); padding: 8px 10px; border-radius: 6px;
    background: var(--input-fill-color, var(--secondary-background-color)); border: 1px solid var(--divider-color);
  }
  .scan-status {
    padding: 12px 14px; border-radius: 8px; font-size: 16px;
    background: var(--secondary-background-color); display: flex; flex-direction: column; gap: 10px;
  }
  .scan-status.ok { background: rgba(76,175,80,.2); }
  .scan-status.warn { background: rgba(255,152,0,.2); }
  .scan-status.error { background: rgba(244,67,54,.2); }
  .scan-status .actions { margin-top: 0; }
  .scan-log { list-style: none; margin: 0; padding: 0; font-size: 14px; }
  .scan-log li { padding: 4px 0; border-bottom: 1px solid var(--divider-color); }
  @media (max-width: 700px) {
    .wide { display: none; }
    .row.unknown { grid-template-columns: 1fr; }
  }
`;

if (!customElements.get("espeep-panel")) customElements.define("espeep-panel", EspeepPanel);
