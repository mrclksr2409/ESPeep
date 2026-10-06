# ESPeep

Scan a product's barcode, and it lands on your Home Assistant shopping list
under a name you actually recognise.

An ESP32 with a cheap UART barcode module, an OLED and a buzzer, mounted where
you unpack or use up groceries. Point, beep, done — the empty milk carton goes
in the bin and "Milch" is on the list before you have put the lid down.

```
scan ──▶ ESP32 ──▶ Home Assistant ──▶ your to-do list
           ▲          │  ESPeep integration:
           │          │   your names ▸ Open Food Facts ▸ ask you
           └──────────┘
        OLED shows what landed on the list
```

ESPeep has two halves:

- **the device** — ESPHome firmware, flashed from the ESPHome dashboard. It
  reads and validates barcodes, nothing more.
- **the ESPeep integration** — installed through HACS. It keeps the product
  database, looks barcodes up, fills the list and asks you about unknown
  products. Everything is managed from the **ESPeep panel** in the sidebar.

## What makes it usable day to day

- **You see what it got.** The OLED shows the resolved product name at the
  shelf. A scanner that silently adds the wrong thing is worse than no scanner.
- **Your names, not the database's.** Open Food Facts calls it "Ja! Haltbare
  Fettarme Milch 1,5% 1l". Your list says "Milch". Rename it once in the
  ESPeep panel and that is what every future scan puts on the list.
- **Unknown products get learned once.** Not in any database? Your phone asks
  what to call it — or you name it in the panel — and the answer is stored.
- **Managed in Home Assistant, not in YAML.** Add, edit, search, import and
  export barcodes in the sidebar panel. No files to edit, no restarts.
- **Misreads do not reach your list.** Every barcode is check-digit validated
  on the device.
- **No duplicates.** Scanning the same product on two shopping trips does not
  put it on the list twice.
- **Almost any scanner works.** The firmware reads lines of ASCII from a UART
  rather than driving one specific module. GM60 is the reference; GM65, GM66,
  GM67, GM77, GM805-L and DE2120 work the same way.

## Hardware

Roughly 30 € in total. Full list and wiring in [docs/hardware.md](docs/hardware.md).

| | |
|---|---|
| ESP32 dev board | ESP32-DevKitC, NodeMCU-32S or D1 Mini ESP32 |
| UART barcode module | GM60 (reference), GM65/GM67 and others — [docs/scanner-modules.md](docs/scanner-modules.md) |
| SSD1306 OLED 0.96", I²C | shows the product name |
| **Passive** piezo buzzer | different tone per outcome |
| 5 V USB supply | ESPeep stays plugged in; no battery, no deep sleep |

## Getting started

1. **Build it** — wiring in [docs/hardware.md](docs/hardware.md). Check the
   baud rate of your scanner in [docs/scanner-modules.md](docs/scanner-modules.md):
   GM60 is 57600, GM65/GM67 are 9600.
2. **Install the integration** — in HACS, add
   `https://github.com/mrclksr2409/ESPeep` as a custom repository of type
   *Integration*, install **ESPeep**, restart Home Assistant.
3. **Flash the device** — in the ESPHome dashboard, create a new ESP32 device
   and add the ESPeep packages to it: [docs/esphome.md](docs/esphome.md).
   Adopt it in Home Assistant when it is discovered.
4. **Connect them** — *Settings → Devices & Services → Add integration →
   ESPeep*: pick the device, your to-do list and, optionally, your phone.
   [docs/home-assistant.md](docs/home-assistant.md)

Scan something. Not getting anything out of the scanner? Turn on the **Raw
UART Debug** switch and read [docs/troubleshooting.md](docs/troubleshooting.md)
— it is almost always the baud rate or swapped RX/TX.

## How it fits together

| Where | What it does |
|---|---|
| `custom_components/espeep/` | The Home Assistant integration (HACS): product database, lookup, to-do list, panel |
| `esphome/packages/` | The firmware, as ESPHome packages |
| `esphome/espeep-dashboard.yaml` | Device file for the ESPHome dashboard — pulls the packages from GitHub |
| `esphome/espeep.yaml` | Device file for the ESPHome command line, with every setting explained |
| `tests/` | Integration tests against a real Home Assistant core, and the firmware's barcode and display logic |
| `docs/` | Hardware, flashing, Home Assistant, scanner modules, troubleshooting |

The device sends each valid barcode to Home Assistant; the integration answers
with the name that landed on the list, and the OLED shows it. Because all the
knowledge lives in Home Assistant, renaming a product never means reflashing.

## Documentation

- [Hardware and wiring](docs/hardware.md)
- [Flashing with ESPHome](docs/esphome.md)
- [Scanner modules and how to switch one to UART](docs/scanner-modules.md)
- [Home Assistant integration and panel](docs/home-assistant.md)
- [Troubleshooting](docs/troubleshooting.md)

## Credits

Open Food Facts provides the product database — a community project worth
[contributing to](https://world.openfoodfacts.org/) when you scan something it
does not know yet. The approach of pairing an ESPHome scanner with a Home
Assistant to-do list was shown by
[MattFryer/HA-Mealie-Barcode-Scanner](https://github.com/MattFryer/HA-Mealie-Barcode-Scanner)
and [SmartHome-yourself/barcode-scanner-for-esphome](https://github.com/SmartHome-yourself/barcode-scanner-for-esphome).
