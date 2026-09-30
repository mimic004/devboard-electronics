// probe.ino - vendored line-protocol peripheral probe for ESP32 / ESP32-S3.
//
// Written against core arduino-esp32 APIs only: no vendor forks, no third-party
// libraries, nothing that has to be installed before a board can be questioned.
//
// It speaks a LINE PROTOCOL rather than printing prose, so the host can parse it
// deterministically instead of scraping English:
//
//     > PROBE i2c 39 38 100000
//     < probe.i2c.begin ok
//     < probe.i2c.found 0x20
//     < probe.i2c.found 0x5a
//     < probe.i2c.elapsed_ms 41
//     < probe.done i2c ok
//
// Every response starts with "probe.", every run ends with exactly one
// "probe.done <name> ok|fail", and every measurement is emitted as its own
// "probe.<name>.<key> <value>" line.
//
// THREE RULES THIS SKETCH DOES NOT BREAK
//
//   1. Every busy-wait has a timeout. Vendor drivers routinely spin forever, so
//      a peripheral that never releases BUSY hangs the device with the rail up.
//
//   2. Wait for a busy line to ASSERT before waiting for it to release. That is
//      what distinguishes "finished quickly" from "never started" - and it is
//      exactly the check that would have caught a 29 ms e-paper refresh that
//      "succeeded" while the panel controller was unpowered.
//
//   3. Report elapsed time for everything. The host owns the plausibility
//      bounds; the sketch's job is to make the timing visible so an implausibly
//      good result can be caught and failed.
//
// Build:
//     arduino-cli compile --fqbn <your board fqbn> --warnings all firmware/probe
// Drive it:
//     probe_client.py <probe-spec.json> --port COM7

#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>

static const uint32_t SERIAL_BAUD = 115200;
static const uint32_t DEFAULT_BUSY_TIMEOUT_MS = 5000;

// ---------------------------------------------------------------------------
// output helpers - one fact per line, never prose
// ---------------------------------------------------------------------------

static void emit(const char *name, const char *key, const String &value) {
  Serial.print("probe.");
  Serial.print(name);
  Serial.print('.');
  Serial.print(key);
  Serial.print(' ');
  Serial.println(value);
}

static void emitU32(const char *name, const char *key, uint32_t value) {
  emit(name, key, String(value));
}

static void done(const char *name, bool ok) {
  Serial.print("probe.done ");
  Serial.print(name);
  Serial.println(ok ? " ok" : " fail");
}

static void fail(const char *name, const char *reason) {
  emit(name, "error", String(reason));
  done(name, false);
}

static String hex2(uint8_t v) {
  char buf[5];
  snprintf(buf, sizeof(buf), "0x%02x", v);
  return String(buf);
}

// ---------------------------------------------------------------------------
// token helpers
// ---------------------------------------------------------------------------

static String argAt(const String &line, int index) {
  int start = 0, count = 0;
  while (start < (int)line.length()) {
    int sp = line.indexOf(' ', start);
    if (sp < 0) sp = line.length();
    if (count == index) return line.substring(start, sp);
    count++;
    start = sp + 1;
  }
  return String();
}

static long argInt(const String &line, int index, long fallback) {
  String s = argAt(line, index);
  if (s.length() == 0) return fallback;
  return s.toInt();
}

// ---------------------------------------------------------------------------
// probes
// ---------------------------------------------------------------------------

// PROBE i2c <sda> <scl> [hz]
// Scans the bus and reports EVERY address that answers. The host compares the
// set against an EXACT expected set, not a superset: an unexpected device is as
// interesting as a missing one.
static void probeI2c(const String &line) {
  const char *n = "i2c";
  int sda = (int)argInt(line, 2, -1);
  int scl = (int)argInt(line, 3, -1);
  uint32_t hz = (uint32_t)argInt(line, 4, 100000);
  if (sda < 0 || scl < 0) { fail(n, "usage:PROBE i2c <sda> <scl> [hz]"); return; }

  Wire.end();
  if (!Wire.begin(sda, scl, hz)) { fail(n, "begin-failed"); return; }
  emit(n, "begin", "ok");
  emitU32(n, "sda", (uint32_t)sda);
  emitU32(n, "scl", (uint32_t)scl);
  emitU32(n, "hz", hz);

  uint32_t t0 = millis();
  int found = 0;
  for (uint8_t addr = 0x08; addr <= 0x77; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      emit(n, "found", hex2(addr));
      found++;
    }
    delay(1);
  }
  emitU32(n, "count", (uint32_t)found);
  emitU32(n, "elapsed_ms", millis() - t0);

  // A scan that finds nothing is a RESULT, not an error: it usually means no
  // pull-ups, the wrong pins, or an unpowered rail. The host decides.
  done(n, true);
}

// PROBE gpio sweep
// Reports which candidate pins are already driven by something on the board.
// Any pin that reads HELD is not yours, whatever the pinout diagram says.
static void probeGpio(const String &line) {
  const char *n = "gpio";
  String mode = argAt(line, 2);
  if (mode != "sweep") { fail(n, "usage:PROBE gpio sweep"); return; }

  uint32_t t0 = millis();
  int held = 0, freePins = 0;
  for (int pin = 0; pin <= 48; pin++) {
#if defined(SOC_GPIO_VALID_GPIO_MASK)
    if (!GPIO_IS_VALID_GPIO(pin)) continue;
#endif
    pinMode(pin, INPUT_PULLUP);
    delayMicroseconds(200);
    int up = digitalRead(pin);
    pinMode(pin, INPUT_PULLDOWN);
    delayMicroseconds(200);
    int down = digitalRead(pin);
    pinMode(pin, INPUT);

    // Follows both pulls => nothing else is driving it.
    if (up == HIGH && down == LOW) {
      emit(n, "free", String(pin));
      freePins++;
    } else {
      emit(n, "held", String(pin) + " " + String(up == HIGH ? "high" : "low"));
      held++;
    }
  }
  emitU32(n, "free_count", (uint32_t)freePins);
  emitU32(n, "held_count", (uint32_t)held);
  emitU32(n, "elapsed_ms", millis() - t0);
  done(n, true);
}

// PROBE adc <pin>
// Raw and scaled, plus the caveat that matters: on USB the charger holds the
// battery node at its float voltage whether a cell is fitted or not.
static void probeAdc(const String &line) {
  const char *n = "adc";
  int pin = (int)argInt(line, 2, -1);
  if (pin < 0) { fail(n, "usage:PROBE adc <pin>"); return; }

  uint32_t t0 = millis();
  uint32_t sum = 0;
  const int samples = 16;
  for (int i = 0; i < samples; i++) { sum += analogRead(pin); delay(2); }
  uint32_t raw = sum / samples;

  emitU32(n, "pin", (uint32_t)pin);
  emitU32(n, "raw", raw);
  emitU32(n, "mv", (uint32_t)analogReadMilliVolts(pin));
  emitU32(n, "samples", (uint32_t)samples);
  emitU32(n, "elapsed_ms", millis() - t0);
  emit(n, "caveat", "on-usb-the-charger-holds-vbat-at-float");
  done(n, true);
}

// PROBE buttons <pin> <ms>
// Captures debounced transitions. A button that never transitions has not been
// proven to work - a steady level proves nothing.
static void probeButtons(const String &line) {
  const char *n = "buttons";
  int pin = (int)argInt(line, 2, -1);
  uint32_t window = (uint32_t)argInt(line, 3, 5000);
  if (pin < 0) { fail(n, "usage:PROBE buttons <pin> <ms>"); return; }

  pinMode(pin, INPUT_PULLUP);
  emitU32(n, "pin", (uint32_t)pin);
  emitU32(n, "window_ms", window);

  int last = digitalRead(pin);
  emit(n, "initial", String(last == HIGH ? "high" : "low"));

  uint32_t t0 = millis(), lastChange = 0;
  int transitions = 0;
  while (millis() - t0 < window) {
    int now = digitalRead(pin);
    if (now != last && (millis() - lastChange) > 15) {  // 15 ms debounce
      emit(n, "edge", String(millis() - t0) + " " + String(now == LOW ? "press" : "release"));
      lastChange = millis();
      last = now;
      transitions++;
    }
    delay(1);
  }
  emitU32(n, "transitions", (uint32_t)transitions);
  emitU32(n, "elapsed_ms", millis() - t0);
  // Deliberately NOT a failure here: the host's requires_transition rule decides
  // whether zero transitions means "broken" or "nobody pressed it".
  done(n, true);
}

// PROBE rail <pin> <high|low>
// Toggles a gated rail and reports the state change. The point is the
// TRANSITION, not the final level.
static void probeRail(const String &line) {
  const char *n = "rail";
  int pin = (int)argInt(line, 2, -1);
  String want = argAt(line, 3);
  if (pin < 0 || (want != "high" && want != "low")) {
    fail(n, "usage:PROBE rail <pin> <high|low>");
    return;
  }
  pinMode(pin, INPUT);
  delay(5);
  int before = digitalRead(pin);
  pinMode(pin, OUTPUT);
  digitalWrite(pin, want == "high" ? HIGH : LOW);
  delay(100);  // settle
  int after = digitalRead(pin);

  emitU32(n, "pin", (uint32_t)pin);
  emit(n, "before", String(before == HIGH ? "high" : "low"));
  emit(n, "after", String(after == HIGH ? "high" : "low"));
  emit(n, "changed", String(before != after ? "yes" : "no"));
  emitU32(n, "settle_ms", 100);
  done(n, true);
}

// PROBE busy <busy_pin> <trigger_pin> <active_high|active_low> [timeout_ms]
//
// The generic version of the e-paper lesson, and the most important probe here.
//
// It waits for the BUSY line to ASSERT first, and only then waits for it to
// release. A peripheral whose controller is unpowered leaves BUSY floating; the
// naive "wait until not busy" completes instantly and reports success. Waiting
// for the assert turns that silent lie into an explicit never-started failure.
static void probeBusy(const String &line) {
  const char *n = "busy";
  int busyPin = (int)argInt(line, 2, -1);
  int trigPin = (int)argInt(line, 3, -1);
  String sense = argAt(line, 4);
  uint32_t timeout = (uint32_t)argInt(line, 5, DEFAULT_BUSY_TIMEOUT_MS);
  if (busyPin < 0 || trigPin < 0 || (sense != "active_high" && sense != "active_low")) {
    fail(n, "usage:PROBE busy <busy_pin> <trigger_pin> <active_high|active_low> [timeout_ms]");
    return;
  }
  int activeLevel = (sense == "active_high") ? HIGH : LOW;

  pinMode(busyPin, INPUT);
  pinMode(trigPin, OUTPUT);
  emitU32(n, "busy_pin", (uint32_t)busyPin);
  emitU32(n, "trigger_pin", (uint32_t)trigPin);
  emit(n, "sense", sense);
  emitU32(n, "timeout_ms", timeout);

  digitalWrite(trigPin, HIGH);
  uint32_t t0 = millis();

  // 1. Wait for ASSERT, with a timeout. No assert means it never started.
  bool asserted = false;
  while (millis() - t0 < timeout) {
    if (digitalRead(busyPin) == activeLevel) { asserted = true; break; }
    delay(1);
  }
  uint32_t assertMs = millis() - t0;
  emit(n, "asserted", String(asserted ? "yes" : "no"));
  emitU32(n, "assert_ms", assertMs);

  if (!asserted) {
    emit(n, "diagnosis", "busy-never-asserted-peripheral-probably-unpowered");
    fail(n, "never-started");
    return;
  }

  // 2. Only now wait for RELEASE, also with a timeout.
  uint32_t t1 = millis();
  bool released = false;
  while (millis() - t1 < timeout) {
    if (digitalRead(busyPin) != activeLevel) { released = true; break; }
    delay(1);
  }
  uint32_t busyMs = millis() - t1;
  emit(n, "released", String(released ? "yes" : "no"));
  emitU32(n, "busy_ms", busyMs);
  emitU32(n, "elapsed_ms", millis() - t0);

  if (!released) {
    emit(n, "diagnosis", "busy-never-released-within-timeout");
    fail(n, "stuck-busy");
    return;
  }
  // The host still applies its plausibility band to busy_ms. A success that is
  // far too fast is a FAULT, and only the host knows what "too fast" is.
  done(n, true);
}

// PROBE spi <sck> <mosi> <miso> <cs>
// Loopback test: tie MOSI to MISO to prove the bus moves bytes at all before
// blaming a device.
static void probeSpi(const String &line) {
  const char *n = "spi";
  int sck = (int)argInt(line, 2, -1);
  int mosi = (int)argInt(line, 3, -1);
  int miso = (int)argInt(line, 4, -1);
  int cs = (int)argInt(line, 5, -1);
  if (sck < 0 || mosi < 0 || miso < 0) { fail(n, "usage:PROBE spi <sck> <mosi> <miso> <cs>"); return; }

  SPIClass spi(HSPI);
  spi.begin(sck, miso, mosi, cs);
  if (cs >= 0) { pinMode(cs, OUTPUT); digitalWrite(cs, LOW); }

  uint32_t t0 = millis();
  const uint8_t pattern[4] = {0x00, 0xA5, 0x5A, 0xFF};
  int matched = 0;
  spi.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  for (int i = 0; i < 4; i++) {
    uint8_t got = spi.transfer(pattern[i]);
    emit(n, "xfer", hex2(pattern[i]) + " " + hex2(got));
    if (got == pattern[i]) matched++;
  }
  spi.endTransaction();
  if (cs >= 0) digitalWrite(cs, HIGH);
  spi.end();

  emitU32(n, "matched", (uint32_t)matched);
  emitU32(n, "elapsed_ms", millis() - t0);
  emit(n, "note", "loopback-requires-mosi-tied-to-miso");
  done(n, matched == 4);
}

// PROBE sleep <seconds>
// Prints the metering procedure, then actually sleeps. The measurement is made
// with an instrument, not by this sketch - a chip cannot honestly measure its
// own sleep current.
static void probeSleep(const String &line) {
  const char *n = "sleep";
  uint32_t secs = (uint32_t)argInt(line, 2, 30);
  emitU32(n, "seconds", secs);
  emit(n, "procedure", "meter-in-series-with-battery-positive-uA-range-USB-DISCONNECTED");
  emit(n, "warning", "a-reading-taken-over-usb-is-not-sleep-current");
  Serial.flush();
  done(n, true);
  delay(50);
  esp_sleep_enable_timer_wakeup((uint64_t)secs * 1000000ULL);
  esp_deep_sleep_start();
}

// ID - identity, so a transcript can be tied to a specific board.
static void probeId() {
  const char *n = "id";
  emit(n, "chip", String(ESP.getChipModel()));
  emitU32(n, "revision", (uint32_t)ESP.getChipRevision());
  emitU32(n, "cores", (uint32_t)ESP.getChipCores());
  emitU32(n, "flash_bytes", ESP.getFlashChipSize());
  emitU32(n, "psram_bytes", ESP.getPsramSize());
  emit(n, "psram_note", "zero-usually-means-BOARD_HAS_PSRAM-undefined-not-a-fault");
  emit(n, "sdk", String(ESP.getSdkVersion()));
  emit(n, "probe_version", "1.0");
  done(n, true);
}

static void probeHelp() {
  Serial.println("probe.help i2c <sda> <scl> [hz]");
  Serial.println("probe.help gpio sweep");
  Serial.println("probe.help adc <pin>");
  Serial.println("probe.help buttons <pin> <ms>");
  Serial.println("probe.help rail <pin> <high|low>");
  Serial.println("probe.help busy <busy_pin> <trigger_pin> <active_high|active_low> [timeout_ms]");
  Serial.println("probe.help spi <sck> <mosi> <miso> <cs>");
  Serial.println("probe.help sleep <seconds>");
  Serial.println("probe.done help ok");
}

// ---------------------------------------------------------------------------

static void dispatch(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.equalsIgnoreCase("ID")) { probeId(); return; }
  if (line.equalsIgnoreCase("HELP")) { probeHelp(); return; }

  if (!line.startsWith("PROBE ")) {
    Serial.print("probe.error unknown-command ");
    Serial.println(line);
    return;
  }

  String what = argAt(line, 1);
  if (what == "i2c")          probeI2c(line);
  else if (what == "gpio")    probeGpio(line);
  else if (what == "adc")     probeAdc(line);
  else if (what == "buttons") probeButtons(line);
  else if (what == "rail")    probeRail(line);
  else if (what == "busy")    probeBusy(line);
  else if (what == "spi")     probeSpi(line);
  else if (what == "sleep")   probeSleep(line);
  else {
    Serial.print("probe.error unknown-probe ");
    Serial.println(what);
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);  // bounded: never spin forever
  Serial.println();
  Serial.println("probe.ready 1.0");
  Serial.println("probe.hint send HELP for the command list");
}

void loop() {
  static String buf;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (buf.length()) { dispatch(buf); buf = ""; }
    } else if (buf.length() < 160) {
      buf += c;
    }
  }
  delay(2);
}
