# Hardware

## Part list

| Part | Notes | approx. |
|---|---|---|
| ESP32 dev board | ESP32-DevKitC, NodeMCU-32S or D1 Mini ESP32. Any classic ESP32 works — two spare hardware UARTs means the scanner gets a real one and the USB log stays usable. An ESP32-S3 works too. **ESP8266 is not supported**: its single usable UART collides with the log. | 6 € |
| UART barcode module | GM60, GM65, GM66, GM67, GM77, GM805-L, DE2120 … see [scanner-modules.md](scanner-modules.md) | 15–25 € |
| SSD1306 OLED, 0.96", I²C | The 4-pin I²C version, not the 7-pin SPI one | 4 € |
| **Passive** piezo buzzer | Must be passive. An active buzzer only knows on/off and plays every tune as the same beep | 1 € |
| USB power supply, 5 V / ≥ 1 A | ESPeep is designed to stay plugged in — no battery, no deep sleep | 5 € |
| Dupont wires, small enclosure | | |

## Wiring

Defaults from `esphome/espeep.yaml`. Change the substitutions there if you wire
it differently.

| Signal | ESP32 pin | Goes to |
|---|---|---|
| Scanner RX | `GPIO16` | Scanner **TX** |
| Scanner TX | `GPIO17` | Scanner **RX** |
| Scanner VCC | 5 V or 3V3 | see the warning below |
| Scanner GND | GND | Scanner GND |
| OLED SDA | `GPIO21` | OLED SDA |
| OLED SCL | `GPIO22` | OLED SCL |
| OLED VCC | 3V3 | OLED VCC |
| OLED GND | GND | OLED GND |
| Buzzer + | `GPIO25` | Buzzer + |
| Buzzer − | GND | Buzzer − |
| Status LED | `GPIO2` | onboard LED on most boards |

RX and TX cross over. This is the single most common wiring mistake: the
scanner's TX goes to the ESP's RX pin, not to its TX pin.

> **Check the supply voltage in your module's datasheet before wiring it.**
> The GM6x family ships in 3.3 V and 5 V variants. The signal levels are 3.3 V
> TTL on both, so no level shifter is needed for the data lines — but feeding
> 5 V to a 3.3 V-only module will destroy it.

The scan engine draws a noticeable current spike when its illumination LED
fires. If the ESP32 browns out or reboots on every scan, that is the cause:
power the scanner from the 5 V rail of a supply that can deliver at least 1 A,
not from a laptop USB port, and put a 100 µF electrolytic capacitor across the
scanner's supply pins.

## Where to put it

ESPeep is meant to be mounted where you unpack or use up groceries — the inside
of a pantry door, next to the bin, above the worktop. The point of the fixed
installation is that scanning is a one-handed reflex as you throw the empty
packet away, not a task you go and fetch a device for.

Mount it so the scan window points slightly downward at about chest height and
leave 5–15 cm of working distance in front of the lens.

## Assembly notes

- Give the OLED and the scanner a common ground with the ESP32 — a floating
  ground shows up as an OLED that stays dark and a scanner that returns
  garbage.
- The i²c bus is scanned at boot and the addresses found are printed in the
  log. If your OLED is at `0x3D` instead of `0x3C`, set `oled_address` in
  `esphome/espeep.yaml`.
- Route the buzzer wires away from the UART lines. It is a small thing, but a
  loud passive buzzer next to an unshielded 9600 baud line does cause misreads
  — which the check digit test then rejects, so you see "Prüfziffer falsch"
  rather than wrong items on your list.
