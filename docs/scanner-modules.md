# Scanner modules

ESPeep does not contain a driver for any particular scanner. It reads lines of
ASCII from a UART and validates them as barcodes. Every module that can be put
into TTL serial mode therefore works, and adapting to a new one is usually a
matter of setting `scanner_baud` in `esphome/espeep.yaml`.

## Known modules

Verified against the manufacturer manuals. "Interface" is what the module does
out of the box.

| Module | Default baud | Interface out of the box | Supply | Notes |
|---|---|---|---|---|
| **GM60** | **57600** 8N1 | UART/TTL only | 3.3 V | The reference module for this project. Nothing to switch — wire it up and set `scanner_baud: "57600"`. |
| GM65 | 9600 8N1 | USB **and** TTL, ships in USB mode | 3.3–5 V | Must be switched to TTL with a setting code, see below |
| GM65-S | 9600 8N1 | USB and TTL, ships in USB mode | 3.3–5 V | as GM65 |
| GM66 | 9600 8N1 | USB and TTL, ships in USB mode | 3.3–5 V | as GM65 |
| GM67 | 9600 8N1 | USB and TTL, ships in USB mode | 3.3–5 V | Larger scan window, best read rate of the family |
| GM77 | 9600 8N1 | USB and TTL, ships in USB mode | 3.3–5 V | as GM65 |
| GM805-L | 9600 8N1 | USB and TTL | 3.3–5 V | Compact, good for a slim enclosure |
| DE2120 | 9600 8N1 | USB and TTL | 3.3–5 V | Different vendor, same line-of-ASCII behaviour |

All of them read EAN-13, EAN-8, UPC-A, UPC-E, Code 128, Code 39, ITF and QR —
far more than ESPeep needs, which only accepts 8, 12, 13 and 14 digit product
codes.

> The values above are the manufacturer defaults. A second-hand module may have
> been reconfigured by whoever had it before. If in doubt, go through the
> bring-up procedure below rather than trusting the table.

## Switching a module into UART mode

Modules with a USB interface ship in USB-HID mode, where they behave like a
keyboard and send nothing at all over their TX pin. You switch them by
**scanning setting codes printed in the manual** — there is no software command
for it, and it only has to be done once per module.

1. Get the manual for your exact module (Hangzhou Grow Technology publishes
   them as PDFs; search for e.g. "GM67 Bar Code Reader Module User Manual").
2. Scan the **"Serial port (TTL-232)"** setting code — often labelled *UART* or
   *TTL* in the interface section.
3. Optionally scan the baud rate code you want. Leave it at the default unless
   you have a reason to change it.
4. Scan the code that appends a **CR** or **CR-LF suffix** to the output, if
   your module does not do so already. ESPeep treats both CR and LF as line
   terminators and does not care which you pick — but a module that sends no
   terminator at all will never produce a complete line.

## Bringing up an unknown module

This is what the `Raw UART Debug` switch is for. It costs nothing and answers
the two questions that matter — is the module talking at all, and at what baud
rate.

1. Wire it up per [hardware.md](hardware.md) and flash ESPeep.
2. Open the log: `esphome logs espeep.yaml`.
3. Turn on the **Raw UART Debug** switch (it appears in Home Assistant as a
   diagnostic switch on the ESPeep device, or via the ESPHome web interface).
4. Scan any barcode and read the log:

   | What you see | What it means |
   |---|---|
   | `UART byte: 0x34 ('4')` — readable digits | Correct baud rate. Turn the switch off, you are done. |
   | Bytes arrive, but as random-looking values | Wrong baud rate. Try the other candidates from the table (9600, 57600, 115200, 19200, 38400). |
   | `Discarding overlong UART line` | Same as above — wrong baud rate, or the module is streaming continuously. |
   | Nothing at all | The module is not in UART mode, RX/TX are swapped, or it has no power. Check the wiring first, then the interface setting. |

5. Once digits show up, set `scanner_baud` in `esphome/espeep.yaml` to the rate
   that worked and re-flash.

## Adding a module to the table

If you get a module working that is not listed above, a pull request adding a
row — module, baud rate, and which setting codes you had to scan — is welcome.
No code change should be necessary; if one was, that is worth reporting too.
