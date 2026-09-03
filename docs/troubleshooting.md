# Troubleshooting

Work top to bottom — the entries are ordered by how often they are the actual
cause.

## The scanner reads, but nothing happens

Open the log with `esphome logs espeep.yaml` and scan something. What you see
tells you where it stopped.

| Log line | Cause | Fix |
|---|---|---|
| nothing at all | The scanner is not sending on its TX pin | See "Nothing arrives over UART" below |
| `Discarding overlong UART line` | Wrong baud rate, or the module streams continuously | Try the other baud rates, see [scanner-modules.md](scanner-modules.md) |
| `Ignoring barcode with unexpected length` | Not a product barcode — a QR code, a loyalty card, a shelf label | Nothing to fix; ESPeep only accepts 8, 12, 13 and 14 digit codes |
| `Barcode … failed the check digit test` | Misread | See "Check digit errors" below |
| `Accepted barcode …` then nothing | The lookup or Home Assistant side | Check the next sections |

## Nothing arrives over UART

In order of likelihood:

1. **RX and TX are swapped.** The scanner's TX goes to the ESP's RX pin
   (`GPIO16` by default), not to its TX pin. This is the most common mistake.
2. **The module is still in USB-HID mode.** GM65, GM66, GM67 and GM77 ship
   configured as a USB keyboard and send nothing over TTL until you scan the
   setting code that switches them. The GM60 is UART-only and needs no such
   switch. See [scanner-modules.md](scanner-modules.md).
3. **Wrong baud rate.** Turn on the **Raw UART Debug** switch and scan. Bytes
   that arrive but look like noise mean the wiring is right and only the rate
   is wrong. GM60 is 57600, most others are 9600.
4. **No common ground** between the scanner and the ESP32.

## Check digit errors on codes that should be fine

If it happens on every scan, the data is being corrupted in transit:

- The baud rate is *almost* right — some clones deviate. Try neighbouring
  rates.
- The UART wires run alongside the buzzer wires. Separate them.
- The scanner is browning out. Its illumination LED draws a current spike on
  every scan; if the ESP32 reboots or the reads are erratic, use a supply that
  can deliver at least 1 A and add a 100 µF capacitor across the scanner's
  supply pins.

If it happens on one specific product, that barcode is likely damaged or
printed badly. Check it against another scanner or a phone app.

## Display stays dark

- Look for the i²c scan in the boot log. It lists the addresses it found.
  Nothing found means a wiring or power problem; an address other than `0x3C`
  means you need to set `oled_address` in `esphome/espeep.yaml`.
- Make sure it is an **I²C** SSD1306 (4 pins: VCC, GND, SCL, SDA), not the SPI
  variant.

## Buzzer is silent or always the same beep

ESPeep plays a different tune per outcome, which requires a **passive** piezo
buzzer. An active buzzer contains its own oscillator, only understands on and
off, and will render every tune as one flat beep. If yours has a sticker over
the top and beeps when you put 3.3 V across it, it is active — swap it.

## Display says "Kein WLAN" or "Keine Verbindung"

- "Kein WLAN" — the device is not on the network. Check `secrets.yaml`; the
  fallback access point `ESPeep Setup` comes up if the credentials are wrong.
- "Keine Verbindung" — WiFi is up but Open Food Facts could not be reached.
  Usually DNS or an outbound restriction on the network.
- "Server-Fehler HTTP 429" — you are being rate limited. That means an unusual
  number of scans in a short time; it clears on its own.

Note that Home Assistant can still resolve the barcode from your mapping table
when the internet lookup fails — the scan is reported either way.

## Display says "Warte auf HA"

The device is on WiFi but not connected to Home Assistant. Check that the
device is adopted under *Settings → Devices & Services* and that the
`api_encryption_key` in `secrets.yaml` matches what you gave Home Assistant.

## Items do not appear on the list

Test the Home Assistant side without the hardware — *Developer tools → Events
→ Fire event*:

```yaml
event_type: esphome.espeep_scan
event_data:
  ean: "3017620422003"
  name: "Ferrero Nutella"
  brand: "Ferrero"
  quantity: "400 g"
  source: "off"
```

- Nothing happens at all → the package is not loaded. Check that
  `homeassistant: packages: !include_dir_named packages` is in
  `configuration.yaml` and that you restarted (a reload is not enough for a new
  package).
- The automation runs but errors → open its trace. Almost always the
  `list_entity` in `script.espeep_add_item` does not match a real to-do entity.

## The mapping table is ignored

- **The barcode is not quoted.** `4008400202037: Milch` is parsed as a number
  and the leading-zero handling differs; it will never match. Write
  `"4008400202037": "Milch"`.
- **Templates were not reloaded.** After editing `ean_mapping.yaml` by hand,
  run the `template.reload` action.
- Check what Home Assistant actually loaded: *Developer tools → Template*:

  ```jinja
  {{ state_attr('sensor.espeep_ean_mapping', 'map') }}
  ```

## The "unknown product" reply is not stored

- Check the exit code in the automation trace. `espeep_remember_ean.sh` refuses
  anything that does not look like a barcode, and refuses names containing a
  double quote.
- Confirm the script is at `/config/espeep_remember_ean.sh` and the mapping
  file at `/config/packages/ean_mapping.yaml` — those paths are hard-coded in
  the `shell_command` and must match where you copied the files.
- A failure raises a persistent notification with the exit code and stderr.

## Same product added twice

ESPeep checks the list before adding, but only against items that are still
open (`needs_action`). An item you already ticked off does not block a new one
— which is intended: you are buying it again.

## Starting over with an unknown module

Turn on **Raw UART Debug** and follow the bring-up procedure in
[scanner-modules.md](scanner-modules.md#bringing-up-an-unknown-module). It
answers both questions that matter — is the module talking, and at what rate —
without changing any firmware.
