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
| `Accepted barcode …` then nothing | The Home Assistant side | Check the next sections |

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

## What the display tells you

| Display | Meaning | Fix |
|---|---|---|
| "Warte auf HA" (idle) | On WiFi, but Home Assistant is not connected | Adopt the device under *Settings → Devices & Services → ESPHome*; check that the API key matches |
| "Kein WLAN" (idle) | Not on the network | Check the WiFi credentials; the fallback access point `ESPeep Setup` comes up if they are wrong |
| "Keine Verbindung zu HA" | A barcode was read while Home Assistant was not connected | As for "Warte auf HA" |
| "Keine Antwort von HA" | The scan was sent, but nobody answered within 15 s | The ESPeep integration is not set up for this device — see below |
| "Keine Verbindung" | Home Assistant could not reach any online product database | Check Home Assistant's internet access. Barcodes already in the product database keep working |
| "Liste nicht erreichbar" | Adding to the to-do list failed | The list entity is unavailable (e.g. Bring! offline) or was removed; check *Settings → Devices & Services → ESPeep → Configure* |
| "In HA benennen" | No database knows the barcode | Name it in the notification on your phone or in the **ESPeep** panel |

## "Keine Antwort von HA" after every scan

The device sends the barcode as the event `esphome.espeep_scan`, and the
ESPeep integration answers. If no answer arrives:

1. Check that the integration is set up **for this device**: *Settings →
   Devices & Services → ESPeep*. Each scanner needs its own entry.
2. Watch the event arrive: *Developer tools → Events*, listen to
   `esphome.espeep_scan`, and scan something. No event means the ESPHome
   connection is the problem; an event with a `device_id` that does not match
   the device you selected means you picked the wrong device in the setup.
3. Simulate a scan without hardware with the action `espeep.scan`
   (*Developer tools → Actions*). Its response tells you exactly what happened.

## Items do not appear on the list

Run the action `espeep.scan` with a barcode, e.g. `3017620422003`, and look at
the response:

- `result: list_failed` → the to-do entity does not work. Check it in
  *Settings → Devices & Services → ESPeep → Configure*, and check the Home
  Assistant log for the reason.
- `result: recognised` → the switch **Add to shopping list** of that scanner is
  off (catalogue mode).
- `result: already_listed` → an open item with the same name is already on the
  list.

## A product gets the wrong name

Open the **ESPeep** panel in the sidebar, search for it and edit the name. Your
name is used from the next scan on and is never overwritten by an online
database. Products marked *online* came from Open Food Facts and friends;
edited ones are marked *eigener Name*.

## The reply on the phone is not stored

- The notification has to come from the ESPeep integration — check that a
  `notify.mobile_app_…` service is selected in the integration's options.
- Text input in notifications needs the Home Assistant companion app; other
  notify services only show the message. Name the barcode in the panel
  instead — it is listed under *Unbekannte Barcodes*.

## Same product added twice

ESPeep checks the list before adding, but only against items that are still
open (`needs_action`). An item you already ticked off does not block a new one
— which is intended: you are buying it again.

## Starting over with an unknown module

Turn on **Raw UART Debug** and follow the bring-up procedure in
[scanner-modules.md](scanner-modules.md#bringing-up-an-unknown-module). It
answers both questions that matter — is the module talking, and at what rate —
without changing any firmware.
