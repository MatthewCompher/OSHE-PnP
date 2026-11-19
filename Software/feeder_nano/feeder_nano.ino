// OSHE-PnP feeder controller (Arduino Nano). One micro servo per tape feeder; one stroke
// (0 -> 90 -> 0 deg) advances the tape one part. Based on the tested single-servo sweep
// (650-2350 us, 1 deg every 5 ms, 250 ms pause at each end, ~2 s per stroke).
//
// Talks to the Pi (pnpvision feeders.py) over USB serial, 115200 baud, newline-terminated:
//   F<n>       queue one stroke on feeder n (1-based)  -> "OK FEED <n> QUEUED", later "OK FEED <n> DONE"
//   A<n>,<deg> move feeder n's servo to an angle (setup/testing) -> "OK A <n> <deg>"
//   ?          -> "STATE BUSY <n>|IDLE QUEUE <k>"
// Strokes run ONE AT A TIME (queued), so two servos never draw current together from the
// Octopus 5 V rail. Servo power: Octopus 5 V + GND; Nano GND must be joined to that GND.

#include <Servo.h>

// ================== WIRING: set to your pins ==================
const int SERVO_PINS[] = {3, 5, 6};          // feeder 1, 2, 3 signal pins
const int N_FEEDERS = sizeof(SERVO_PINS) / sizeof(SERVO_PINS[0]);

// ================== SERVO (from the tested sweep) ==================
const int SERVO_MIN_US = 650;               // 0 deg
const int SERVO_MAX_US = 2350;              // 180 deg
const int REST_ANGLE   = 0;
const int STROKE_ANGLE = 90;
const unsigned long STEP_MS  = 5;           // 1 deg per step
const unsigned long PAUSE_MS = 250;         // at each end

Servo servos[N_FEEDERS];
int angle[N_FEEDERS];

// ================== QUEUE ==================
const int QMAX = 16;
int queue[QMAX];
int qHead = 0, qLen = 0;

// current stroke
int active = -1;                            // feeder index, -1 = idle
int phase = 0;                              // 0 = going out, 1 = pause, 2 = coming back, 3 = final pause
unsigned long lastStep = 0, waitMs = 0;

String line = "";
unsigned long lastBeat = 0;
bool led = false;

void setAngle(int i, int a) {
  angle[i] = constrain(a, 0, 180);
  servos[i].writeMicroseconds(map(angle[i], 0, 180, SERVO_MIN_US, SERVO_MAX_US));
}

bool enqueue(int i) {
  if (qLen >= QMAX) return false;
  queue[(qHead + qLen) % QMAX] = i;
  qLen++;
  return true;
}

void startNext(unsigned long now) {
  if (active >= 0 || qLen == 0) return;
  active = queue[qHead];
  qHead = (qHead + 1) % QMAX;
  qLen--;
  phase = 0;
  lastStep = now;
  waitMs = 0;
}

void updateStroke(unsigned long now) {
  if (active < 0) return;
  if (now - lastStep < waitMs) return;
  lastStep = now;
  waitMs = STEP_MS;
  int i = active;
  if (phase == 0) {                                   // out to 90
    if (angle[i] < STROKE_ANGLE) setAngle(i, angle[i] + 1);
    if (angle[i] >= STROKE_ANGLE) { phase = 1; waitMs = PAUSE_MS; }
  } else if (phase == 1) {
    phase = 2;
  } else if (phase == 2) {                            // back to 0
    if (angle[i] > REST_ANGLE) setAngle(i, angle[i] - 1);
    if (angle[i] <= REST_ANGLE) { phase = 3; waitMs = PAUSE_MS; }
  } else {                                            // settled
    Serial.print("OK FEED "); Serial.print(i + 1); Serial.println(" DONE");
    active = -1;
  }
}

void handle(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  char c = cmd.charAt(0);
  if (c == 'F' || c == 'f') {
    int n = cmd.substring(1).toInt();
    if (n < 1 || n > N_FEEDERS) { Serial.print("ERR bad feeder "); Serial.println(n); return; }
    if (!enqueue(n - 1)) { Serial.println("ERR queue full"); return; }
    Serial.print("OK FEED "); Serial.print(n); Serial.println(" QUEUED");
  } else if (c == 'A' || c == 'a') {
    int comma = cmd.indexOf(',');
    int n = cmd.substring(1, comma).toInt();
    int a = cmd.substring(comma + 1).toInt();
    if (comma < 0 || n < 1 || n > N_FEEDERS) { Serial.println("ERR use A<n>,<deg>"); return; }
    if (active == n - 1) { Serial.println("ERR feeder busy"); return; }
    setAngle(n - 1, a);
    Serial.print("OK A "); Serial.print(n); Serial.print(" "); Serial.println(angle[n - 1]);
  } else if (c == '?') {
    Serial.print("STATE ");
    if (active >= 0) { Serial.print("BUSY "); Serial.print(active + 1); } else Serial.print("IDLE");
    Serial.print(" QUEUE "); Serial.println(qLen);
  } else {
    Serial.print("ERR unknown: "); Serial.println(cmd);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  for (int i = 0; i < N_FEEDERS; i++) {
    servos[i].attach(SERVO_PINS[i], SERVO_MIN_US, SERVO_MAX_US);
    setAngle(i, REST_ANGLE);
  }
  line.reserve(32);
  Serial.println("OK FEEDER NANO READY");
}

void loop() {
  unsigned long now = millis();
  if (now - lastBeat >= 500) { lastBeat = now; led = !led; digitalWrite(LED_BUILTIN, led); }
  startNext(now);
  updateStroke(now);
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (line.length() > 0) { handle(line); line = ""; }
    } else {
      line += ch;
      if (line.length() > 30) line = "";
    }
  }
}
