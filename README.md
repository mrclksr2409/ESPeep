# ESPeep

Scan a product's barcode, and it lands on your Home Assistant shopping list
under a name you actually recognise.

An ESP32 with a cheap UART barcode module, an OLED and a buzzer, mounted where
you unpack or use up groceries. Point, beep, done — the empty milk carton goes
in the bin and "Milch" is on the list before you have put the lid down.

```
scan ──▶ ESP32 ──▶ Open Food Facts ──▶ OLED shows the product
                        │
                        └──▶ Home Assistant ──▶ your to-do list
                                   │
                                   └── your own name for it wins
```

## What makes it usable day to day

- **You see what it got.** The OLED shows the resolved product name at the
  shelf. A scanner that silently adds the wrong thing is worse than no scanner.
- **Your names, not the database's.** Open Food Facts calls it "Ja! Haltbare
  Fettarme Milch 1,5% 1l". Your list says "Milch". A mapping table in this
  repo overrides the database, per barcode.
- **Unknown products get learned once.** Not in any database? Your phone asks
  what to call it, and the answer is stored — the next scan is instant.
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

```bash
git clone https://github.com/mrclksr2409/ESPeep.git
cd ESPeep/esphome
cp secrets.yaml.example secrets.yaml   # fill in WiFi, API key, OTA password
```

1. Wire it up per [docs/hardware.md](docs/hardware.md).
2. Check the baud rate for your module in
   [docs/scanner-modules.md](docs/scanner-modules.md) and set `scanner_baud`
   in `esphome/espeep.yaml`. GM60 is 57600, GM65/GM67 are 9600.
3. `esphome run espeep.yaml`
4. Set up the Home Assistant side —
   [docs/home-assistant.md](docs/home-assistant.md). You need to fill in your
   to-do list entity and your phone's notify service; both are marked in the
   package file.

Not getting anything out of the scanner? Turn on the **Raw UART Debug** switch
and read [docs/troubleshooting.md](docs/troubleshooting.md) — it is almost
always the baud rate or swapped RX/TX.

## How it fits together

| Where | What it does |
|---|---|
| `esphome/` | Firmware. `espeep.yaml` holds every setting; `packages/` holds the parts |
| `homeassistant/` | To-do list automation, mapping table, notification round trip |
| `tests/` | Barcode validation and display wrapping, runnable without hardware |
| `docs/` | Hardware, scanner modules, Home Assistant setup, troubleshooting |

The barcode lookup runs **on the device** so the name appears on the OLED
without waiting for a round trip. Home Assistant still decides what goes on the
list: your mapping table beats Open Food Facts, and it pushes the final wording
back to the display.

## Documentation

- [Hardware and wiring](docs/hardware.md)
- [Scanner modules and how to switch one to UART](docs/scanner-modules.md)
- [Home Assistant setup](docs/home-assistant.md)
- [Troubleshooting](docs/troubleshooting.md)

## Credits

Open Food Facts provides the product database — a community project worth
[contributing to](https://world.openfoodfacts.org/) when you scan something it
does not know yet. The approach of pairing an ESPHome scanner with a Home
Assistant to-do list was shown by
[MattFryer/HA-Mealie-Barcode-Scanner](https://github.com/MattFryer/HA-Mealie-Barcode-Scanner)
and [SmartHome-yourself/barcode-scanner-for-esphome](https://github.com/SmartHome-yourself/barcode-scanner-for-esphome).
