# Flashing the device with ESPHome

The firmware is plain ESPHome. It reads barcodes, checks them and hands them to
Home Assistant; the ESPeep integration does the rest. There are two ways to
build it.

## With the ESPHome dashboard (Home Assistant add-on) — recommended

You do not need a copy of this repository: the firmware packages are pulled
straight from GitHub.

1. Install the **ESPHome Device Builder** add-on if you do not have it
   (*Settings → Add-ons → Add-on store*).
2. Open it, **+ New device**, name it (e.g. `espeep`), choose **ESP32**.
   The dashboard creates a device file with your WiFi credentials, an API key
   and an OTA password. Skip the install it offers.
3. **Edit** the new device. Keep the `api:`, `ota:` and `wifi:` blocks the
   dashboard generated, and add the `substitutions:` and `packages:` sections
   from [`esphome/espeep-dashboard.yaml`](../esphome/espeep-dashboard.yaml):

   ```yaml
   substitutions:
     device_name: espeep        # the name you gave the device
     friendly_name: ESPeep
     scanner_baud: "57600"      # GM60: 57600, GM65/66/67/77: 9600

   packages:
     espeep:
       url: https://github.com/mrclksr2409/ESPeep
       ref: main
       refresh: 1d
       files:
         - esphome/packages/base.yaml
         - esphome/packages/scanner.yaml
         - esphome/packages/display.yaml
         - esphome/packages/feedback.yaml
   ```

   Wired differently from [hardware.md](hardware.md)? Add the matching
   substitutions — all of them are listed and explained in
   [`esphome/espeep.yaml`](../esphome/espeep.yaml).
4. **Install**. The first time over USB (*Plug into this computer* in Chrome or
   Edge, or *Manual download* and [web.esphome.io](https://web.esphome.io)),
   afterwards wirelessly.
5. Home Assistant discovers the device: *Settings → Devices & Services →
   ESPHome → Configure*. It asks for the API key from the device file.

Then set up the integration — [home-assistant.md](home-assistant.md#3-add-the-integration).

**Updates**: `refresh: 1d` makes the dashboard fetch the packages again once a
day. *Install* after an ESPeep release picks up the new firmware. Pin `ref:` to
a release tag, e.g. `ref: v2.0.0`, if you would rather update deliberately.

## With the ESPHome command line

```bash
git clone https://github.com/mrclksr2409/ESPeep.git
cd ESPeep/esphome
cp secrets.yaml.example secrets.yaml   # fill in WiFi, API key, OTA password
esphome run espeep.yaml
```

`espeep.yaml` lists every setting with an explanation and uses the packages
from your checkout.

## What the firmware does — and does not

- reads the scanner over UART and accepts EAN-8, UPC-A, EAN-13 and ITF-14
  codes with a correct check digit; misreads never leave the device
- ignores the same code read again within 3 seconds
- sends the barcode to Home Assistant as the event `esphome.espeep_scan`
- shows what Home Assistant answers, and beeps accordingly
- shows "Keine Antwort von HA" if no answer arrives within 15 seconds

It does **not** look products up itself or know anything about your list —
that all happens in Home Assistant, which is why you can rename products
without ever reflashing.
