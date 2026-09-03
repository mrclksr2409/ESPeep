// Verifies the two pieces of ESPeep logic that are plain C++ and therefore
// testable without the ESP toolchain: barcode validation (scanner.yaml) and
// the display word wrap (display.yaml).
//
// The bodies below are copied verbatim from the C++ ESPHome generated into
// .esphome/build/espeep/src/main.cpp, with the ESPHome calls replaced by
// return values.

#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <cassert>

enum Verdict { REJECT_EMPTY, REJECT_LENGTH, REJECT_CHECKDIGIT, ACCEPT };

// --- verbatim from scanner.yaml / main.cpp -------------------------------
Verdict validate(const std::string &raw, std::string *out) {
  std::string code;
  for (char c : raw) {
    if (c >= '0' && c <= '9')
      code += c;
  }

  if (code.empty())
    return REJECT_EMPTY;

  size_t len = code.length();
  if (len != 8 && len != 12 && len != 13 && len != 14)
    return REJECT_LENGTH;

  int sum = 0;
  for (size_t i = 0; i + 1 < len; i++) {
    int digit = code[len - 2 - i] - '0';
    sum += (i % 2 == 0) ? digit * 3 : digit;
  }
  int expected = (10 - (sum % 10)) % 10;
  if (expected != code[len - 1] - '0')
    return REJECT_CHECKDIGIT;

  *out = code;
  return ACCEPT;
}

// --- verbatim from display.yaml ------------------------------------------
std::vector<std::string> wrap(const std::string &title) {
  std::vector<std::string> lines;
  const size_t line_len = 20;
  std::string rest = title;
  for (int line = 0; line < 3 && !rest.empty(); line++) {
    std::string chunk = rest;
    if (chunk.length() > line_len) {
      size_t split = chunk.rfind(' ', line_len);
      if (split == std::string::npos || split == 0) {
        split = line_len;
        while (split > 0 && ((uint8_t) chunk[split] & 0xC0) == 0x80)
          split--;
      }
      chunk = rest.substr(0, split);
      rest = rest.substr(chunk.length());
    } else {
      rest.clear();
    }
    while (!rest.empty() && rest[0] == ' ')
      rest.erase(0, 1);
    lines.push_back(chunk);
  }
  return lines;
}

static int failures = 0;

void expect(const char *what, const std::string &raw, Verdict want) {
  std::string code;
  Verdict got = validate(raw, &code);
  const char *names[] = {"EMPTY", "LENGTH", "CHECKDIGIT", "ACCEPT"};
  if (got != want) {
    printf("  FAIL  %-34s input=%-20s got=%s want=%s\n", what, raw.c_str(),
           names[got], names[want]);
    failures++;
  } else {
    printf("  ok    %-34s -> %s\n", what, names[got]);
  }
}

int main() {
  printf("Barcode validation\n");
  // Real EAN-13 codes with correct check digits.
  expect("EAN-13 Nutella", "3017620422003", ACCEPT);
  expect("EAN-13 Coca-Cola", "5449000000996", ACCEPT);
  expect("EAN-13 with CR/LF from scanner", "5449000000996\r\n", ACCEPT);
  expect("EAN-13 with scanner prefix junk", "\x02" "5449000000996", ACCEPT);
  expect("EAN-8", "96385074", ACCEPT);
  expect("UPC-A", "036000291452", ACCEPT);
  expect("ITF-14", "10036000291459", ACCEPT);

  // A single wrong digit must not reach the shopping list.
  expect("EAN-13, one digit corrupted", "5449000000986", REJECT_CHECKDIGIT);
  expect("EAN-13, transposed digits", "5449000009096", REJECT_CHECKDIGIT);
  expect("EAN-8, wrong check digit", "96385075", REJECT_CHECKDIGIT);

  expect("too short", "12345", REJECT_LENGTH);
  expect("too long", "123456789012345", REJECT_LENGTH);
  expect("QR code with letters only", "https://example.com", REJECT_EMPTY);
  expect("empty line", "", REJECT_EMPTY);
  expect("whitespace only", "  \r\n", REJECT_EMPTY);

  printf("\nDisplay word wrap (20 chars per line, max 3 lines)\n");
  struct { const char *in; size_t want_lines; } cases[] = {
      {"Milch", 1},
      {"Ferrero Nutella", 1},
      {"Ja! Haltbare Fettarme Milch 1,5% 1l", 3},
      {"Alpro Barista Hafer Drink ungesuesst 1 Liter Packung", 3},
      {"Supercalifragilisticexpialidocious", 2},
      // German product names are the normal case, and umlauts are two bytes
      // each in UTF-8. A split that lands between those two bytes renders as
      // a broken glyph on the OLED.
      {"Müller Weißkäse Körniger Frischkäse Kräuter", 3},
      {"Gutes Land Vollmilch längerfrischäöü", 2},
      // Adversarial: one long word with no space, where the hard cut at byte
      // 20 lands exactly between the two bytes of "ü".
      {"aaaaaaaaaaaaaaaaaaaübcdefgh", 2},
  };
  for (auto &c : cases) {
    std::vector<std::string> lines = wrap(c.in);
    bool overflow = false;
    bool split_mid_codepoint = false;
    for (auto &l : lines) {
      if (l.length() > 20) overflow = true;
      // A UTF-8 continuation byte (10xxxxxx) at the start of a line means the
      // previous line ended in the middle of a character.
      if (!l.empty() && (static_cast<unsigned char>(l[0]) & 0xC0) == 0x80)
        split_mid_codepoint = true;
    }
    if (split_mid_codepoint) {
      printf("  FAIL  %-52s split inside a UTF-8 character\n", c.in);
      failures++;
      continue;
    }
    if (overflow || lines.size() != c.want_lines) {
      printf("  FAIL  %-52s lines=%zu want=%zu overflow=%d\n", c.in,
             lines.size(), c.want_lines, (int) overflow);
      failures++;
    } else {
      printf("  ok    %-52s ->", c.in);
      for (auto &l : lines) printf(" [%s]", l.c_str());
      printf("\n");
    }
  }

  printf("\n%s\n", failures == 0 ? "ALL PASSED" : "THERE WERE FAILURES");
  return failures == 0 ? 0 : 1;
}
