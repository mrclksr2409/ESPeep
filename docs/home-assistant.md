# Home Assistant setup

The device resolves barcodes on its own, but Home Assistant owns the decisions:
your mapping table beats Open Food Facts, the item goes on the to-do list, and
unknown barcodes turn into a question on your phone.

## 1. Adopt the device

After flashing, Home Assistant discovers the ESPHome device automatically
(*Settings → Devices & Services*). Adopt it and paste the
`api_encryption_key` from your `secrets.yaml` when asked.

Check that the action `esphome.espeep_show_result` exists in *Developer tools →
Actions*. If it does not, the device is not connected yet — the display will
also say "Warte auf HA".

## 2. Enable packages

If your `configuration.yaml` does not have it already, add:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

## 3. Copy the files

| From this repo | To your HA config |
|---|---|
| `homeassistant/packages/espeep.yaml` | `config/packages/espeep.yaml` |
| `homeassistant/packages/ean_mapping.yaml` | `config/packages/ean_mapping.yaml` |
| `homeassistant/espeep_remember_ean.sh` | `config/espeep_remember_ean.sh` |

`ean_mapping.yaml` must sit next to `espeep.yaml`: the `!include` in the
package resolves relative to the file containing it.

## 4. Adjust three values

All three are defined in exactly one place, marked with `>>> <<<` in
`espeep.yaml`:

| What | Where | Example |
|---|---|---|
| Your to-do list | `script.espeep_add_item` → `list_entity` | `todo.einkaufsliste` |
| Your phone | `script.espeep_ask_for_name` → `notify_service` | `notify.mobile_app_pixel_9` |
| The device action | `script.espeep_show_result` → the `action:` key | only if you changed `device_name` |

Find the list under *Developer tools → States*, filtered to `todo.` — any
to-do entity works, whether it comes from Local To-do, Bring! or Mealie. Find
the notify service under *Developer tools → Actions*, filtered to
`notify.mobile_app`.

## 5. Restart and check

Restart Home Assistant (the package adds new top-level keys, which a reload
does not pick up). Then verify without touching the hardware — *Developer
tools → Events → Fire event*:

```yaml
event_type: esphome.espeep_scan
event_data:
  ean: "4008400202037"
  name: "Ferrero Nutella"
  brand: "Ferrero"
  quantity: "450 g"
  source: "off"
```

"Ferrero Nutella" should appear on your list. Firing the same event again
should *not* add it twice.

Then try an unknown one — `source: "none"` and an empty `name`:

```yaml
event_type: esphome.espeep_scan
event_data:
  ean: "9999999999993"
  name: ""
  brand: ""
  quantity: ""
  source: "none"
```

That should put a notification with a text field on your phone.

## How resolution works

```
barcode
  ├─ in ean_mapping.yaml?          -> that name wins
  ├─ else: name from Open Food Facts (looked up on the device)
  └─ else: push notification asking you for a name
            └─ your reply is written into ean_mapping.yaml
               and used from then on
```

The mapping table is the reason this stays usable long-term. Open Food Facts
knows the product as "Ja! Haltbare Fettarme Milch 1,5% 1l"; what belongs on a
shopping list is "Milch". Put the short name in `ean_mapping.yaml` and it wins
from the next scan onwards.

Always quote the barcode in that file. Unquoted, YAML reads it as a number and
strips leading zeros, and the lookup silently never matches.

After editing `ean_mapping.yaml` by hand, run the action `template.reload` (or
restart) so the change is picked up.

## About the shell command

Storing an answer from your phone means appending a line to a file, and Home
Assistant has no native action that writes to disk — `shell_command` is the
only built-in way. Two things keep that safe:

- the automation strips the reply down to a fixed character set before passing
  it on, so no quote, backslash, `$` or newline survives
- `espeep_remember_ean.sh` takes the values as **arguments** rather than having
  them interpolated into a shell string, and re-checks them before writing

### If you would rather not run a shell command

Delete the `shell_command:` block and the `espeep_learn_name` automation, and
maintain `ean_mapping.yaml` by hand in git. Unknown barcodes then only produce
the push notification and the "Unbekannt" display — you add the entry yourself
and re-scan. Everything else keeps working unchanged.

## Notes on the implementation

A few choices that are not obvious from reading the YAML:

- **`mode: queued`** on both automations. Scanning three items in a row must
  process all three; `single` would silently drop the second and third.
- **`todo.get_items` before `todo.add_item`.** Without it, scanning the same
  product on two shopping trips puts it on the list twice.
- **The barcode travels in the notification's action name**
  (`ESPEEP_NAME_<barcode>`). It is the only field the companion app reliably
  returns alongside the reply text.
- **`sensor.espeep_ean_mapping` is a YAML template sensor, not a UI helper.**
  A Template Helper created through the UI would be preferable, but its config
  flow has no field for `attributes:`, which is what carries the table.
- **`continue_on_error` on the display callback.** If the device is unplugged
  when Home Assistant answers, the item is still on the list — that is the part
  that matters.
