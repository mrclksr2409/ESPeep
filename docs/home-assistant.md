# Home Assistant integration

ESPeep's brain is a custom integration for Home Assistant. The device reads and
validates barcodes; the integration does everything else:

- keeps the **product database** — barcode → the name you want on the list
- looks up barcodes it does not know yet in **Open Food Facts**, Open Products
  Facts and Open Beauty Facts, and remembers the answer
- puts the product on any **to-do list** — Local To-do, Shopping List, Bring!,
  Mealie, … — without creating duplicates
- **asks you for a name** when nobody knows a barcode, on your phone or in Home
  Assistant
- sends the result back to the **display**

Everything is managed from the **ESPeep panel** in the sidebar. No YAML, no
files to copy, no shell commands.

## 1. Install with HACS

1. *HACS → ⋮ → Custom repositories*, add
   `https://github.com/mrclksr2409/ESPeep` with category **Integration**.
2. Search for **ESPeep** in HACS, install it.
3. Restart Home Assistant.

<details>
<summary>Without HACS</summary>

Copy `custom_components/espeep/` from this repository to
`config/custom_components/espeep/` and restart Home Assistant.
</details>

## 2. Flash and adopt the device

See [esphome.md](esphome.md). Once the device shows up under *Settings →
Devices & Services → ESPHome*, continue here.

## 3. Add the integration

*Settings → Devices & Services → Add integration → ESPeep*.

| Field | What to choose |
|---|---|
| ESPeep device | The ESPHome device you just flashed |
| Shopping list | Any `todo.` entity |
| Phone | Optional. A `notify.mobile_app_…` service: unknown barcodes then arrive as a notification you can type the name into. Without it, you get a Home Assistant notification instead |
| Look up unknown barcodes online | On by default. Off means only the product database is used |
| Put the brand in front of the name | "Ferrero Nutella" instead of "Nutella", for names from the online databases |
| Product name language | Empty uses Home Assistant's language |

Several scanners? Add the integration once per device. They share one product
database, so a product named in the kitchen is known in the cellar too.

All settings can be changed later under *Configure*.

## 4. Try it

Scan something. Or, without the hardware, run the action **ESPeep: Scan** in
*Developer tools → Actions*:

```yaml
action: espeep.scan
data:
  ean: "3017620422003"
```

The response says what happened, and Nutella should be on your list.

## The ESPeep panel

The sidebar entry **ESPeep** is where you manage everything:

- **Unbekannte Barcodes** — barcodes that were scanned but nobody could name.
  Type a name and choose *Speichern + auf Liste*, or look them up online once
  more.
- **Produkt anlegen** — add a barcode by hand. *Online nachschlagen* fills in
  what the databases know, and you shorten the name to what you actually want
  on the list.
- **Produkte** — the whole database: search, edit, delete, or put a product on
  the list with 🛒 without scanning it.
- **Letzte Scans** — what happened on the last scans, and on which scanner.
- **Import / Export** — paste lines like `4008400202037;Milch`, or the contents
  of the old `ean_mapping.yaml`; export as CSV or JSON.

Every barcode is check-digit validated, in the panel just as on the device.

### Scanning with the phone

**📷 Scannen** in the panel's title bar turns your phone into a second
scanner. A phone scan is handled exactly like one from the device: it goes
straight onto the shopping list, the ESPeep's display shows what was listed
and *Letzte Scans* records it under that ESPeep. With more than one ESPeep,
pick in the scanner which one's list and display to use. An unknown barcode
asks for its name right in the scanner; *Später* leaves it under *Unbekannte
Barcodes* and in the notification. Keep scanning, the scanner stays open.

- **Home Assistant app** (Android, iOS): opens the app's own barcode scanner.
  *Kamera im Browser* switches to the camera view below instead.
- **Browser**: a camera view in the panel. Chrome on Android uses the
  browser's built-in barcode detection; Safari, Firefox and desktop browsers
  use the bundled ZXing decoder (`frontend/vendor/`, Apache-2.0).

Browsers only grant camera access to pages served over **HTTPS** (or
`localhost`). If you open Home Assistant as `http://homeassistant.local:8123`,
use the app or HTTPS access (for example Home Assistant Cloud).

The button appears once an ESPeep device is set up: a phone scan uses that
device's list and settings.

## How a barcode is resolved

```
barcode
  ├─ in the product database?   -> that name (yours wins, always)
  ├─ else: online databases     -> name stored in the database, used from now on
  └─ else: ask you              -> phone notification or HA notification
                                   + listed in the panel under "Unbekannte Barcodes"
```

Online results are stored as they come, marked *online*. Rename one in the
panel and it becomes *your* name — the online databases will never overwrite
it. That is how "Ja! Haltbare Fettarme Milch 1,5% 1l" becomes "Milch" for good.

## Entities

Each scanner gets, on its device page:

| Entity | |
|---|---|
| `sensor.<device>_last_scan` | Name of the last scanned product; `ean`, `result` and `source` as attributes |
| `sensor.<device>_unknown_barcodes` | How many barcodes wait for a name — good for a dashboard badge |
| `sensor.<device>_known_products` | Size of the product database (diagnostic) |
| `switch.<device>_add_to_shopping_list` | Off = catalogue mode: scans are resolved and learned, but nothing is put on the list. Handy for the first evening, when you walk through the pantry |

## Actions

| Action | |
|---|---|
| `espeep.scan` | Handle a barcode as if it had been scanned. Returns the outcome |
| `espeep.set_product` | Store a name (and optionally brand and quantity) for a barcode |
| `espeep.remove_product` | Forget a barcode |
| `espeep.get_products` | Return the product database, unknown barcodes and recent scans |

## Event for your own automations

After every scan the integration fires `espeep_scanned`:

```yaml
event_type: espeep_scanned
data:
  ean: "3017620422003"
  name: "Ferrero Nutella"
  result: added        # added | already_listed | recognised | unknown |
                       # lookup_failed | list_failed | invalid
  source: online       # user | online
  device_id: 1a2b3c…
```

For example, to announce unknown products on a speaker:

```yaml
triggers:
  - trigger: event
    event_type: espeep_scanned
    event_data:
      result: unknown
actions:
  - action: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.kueche
      message: "Den Artikel kenne ich nicht. Gib ihm bitte einen Namen."
```

## Coming from the YAML package (ESPeep 1.x)

1. Delete `config/packages/espeep.yaml` and `config/espeep_remember_ean.sh`
   and restart.
2. Install the integration as above and flash the new firmware — the device no
   longer looks products up itself.
3. Open `config/packages/ean_mapping.yaml`, copy its contents into the
   panel's **Import** box and import. Then delete the file.

## Where the data lives

`config/.storage/espeep.products` — included in every Home Assistant backup.
Edit it only through the panel or the actions.
