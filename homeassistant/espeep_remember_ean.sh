#!/usr/bin/env bash
#
# ESPeep — append one "barcode": "name" pair to the EAN mapping table.
#
# Called by the `espeep_remember_ean` shell command in packages/espeep.yaml
# when you answer the "unknown product" push notification.
#
# Usage: espeep_remember_ean.sh <mapping-file> <barcode> <name>
#
# Taking the values as arguments rather than interpolating them into a shell
# string is deliberate: the name comes from a notification reply, and the
# automation already strips everything outside a safe character set. This is
# the second half of that defence — nothing here is re-parsed by a shell.

set -euo pipefail

if [ "$#" -ne 3 ]; then
	echo "usage: $0 <mapping-file> <barcode> <name>" >&2
	exit 2
fi

mapping_file=$1
barcode=$2
name=$3

# The automation guarantees this, but the check is cheap and this script must
# never be the thing that corrupts the mapping file.
if ! printf '%s' "$barcode" | grep -Eq '^[0-9]{8,14}$'; then
	echo "refusing to store '$barcode': not a plausible barcode" >&2
	exit 1
fi

if printf '%s' "$name" | grep -q '"'; then
	echo "refusing to store a name containing a double quote" >&2
	exit 1
fi

if [ ! -f "$mapping_file" ]; then
	echo "mapping file '$mapping_file' does not exist" >&2
	exit 1
fi

# Replacing an existing entry rather than appending a second one keeps the file
# a valid YAML mapping — duplicate keys would silently shadow each other.
if grep -Eq "^\"$barcode\":" "$mapping_file"; then
	tmp=$(mktemp)
	grep -Ev "^\"$barcode\":" "$mapping_file" >"$tmp"
	cat "$tmp" >"$mapping_file"
	rm -f "$tmp"
fi

printf '"%s": "%s"\n' "$barcode" "$name" >>"$mapping_file"
echo "stored $barcode as '$name'"
