/*
 * R1 LED Beacon MCU Firmware (Arduino skeleton)
 *
 * Receives 6-byte serial frames from R1 main controller:
 *   AA 55 msg_id seq brightness checksum
 *
 * Decodes and drives 8 LEDs:
 *   REF D0 D1 D2 D3 D4 SEQ PAR
 *
 * This is R1 internal wired communication, NOT R1/R2 wireless.
 *
 * NOTE: If using analogWrite for brightness control, PWM-capable pins
 *       vary by board.  On Arduino Nano: D3/D5/D6/D9/D10/D11.
 *       On RP2040 Pico: most GPIO pins support PWM.
 *       Adjust LED_PIN values for your specific board.
 */

// --- LED pin definitions (adjust for your board) ---
const int PIN_REF = 2;
const int PIN_D0  = 3;
const int PIN_D1  = 4;
const int PIN_D2  = 5;
const int PIN_D3  = 6;
const int PIN_D4  = 7;
const int PIN_SEQ = 8;
const int PIN_PAR = 9;

const int LED_PINS[] = { PIN_REF, PIN_D0, PIN_D1, PIN_D2, PIN_D3, PIN_D4, PIN_SEQ, PIN_PAR };
const int NUM_LEDS = 8;

// Frame constants
const uint8_t FRAME_HEADER_0 = 0xAA;
const uint8_t FRAME_HEADER_1 = 0x55;
const int     FRAME_LEN      = 6;

// Current LED state (0 or 1 for each LED)
uint8_t led_state[NUM_LEDS];

void setLed(int index, uint8_t on) {
    led_state[index] = on;
    // Use digitalWrite for simple on/off.
    // For brightness control, use analogWrite(pin, brightness) instead.
    digitalWrite(LED_PINS[index], on ? HIGH : LOW);
}

void setErrorFlash() {
    // Briefly flash REF to indicate a bad frame (optional).
    digitalWrite(PIN_REF, LOW);
    delay(50);
    digitalWrite(PIN_REF, led_state[0] ? HIGH : LOW);
}

void setup() {
    Serial.begin(115200);

    for (int i = 0; i < NUM_LEDS; i++) {
        pinMode(LED_PINS[i], OUTPUT);
        led_state[i] = 0;
        digitalWrite(LED_PINS[i], LOW);
    }

    // REF is always on
    setLed(0, 1);
}

void loop() {
    // Wait for frame header byte 0xAA
    if (Serial.available() < 1) return;
    uint8_t b0 = Serial.read();
    if (b0 != FRAME_HEADER_0) return;

    // Wait for second header byte
    while (Serial.available() < 1) {}
    uint8_t b1 = Serial.read();
    if (b1 != FRAME_HEADER_1) {
        setErrorFlash();
        return;
    }

    // Wait for remaining 4 bytes: msg_id, seq, brightness, checksum
    while (Serial.available() < 4) {}
    uint8_t msg_id     = Serial.read();
    uint8_t seq        = Serial.read();
    uint8_t brightness = Serial.read();
    uint8_t checksum   = Serial.read();

    // Validate
    if (msg_id > 31) {
        setErrorFlash();
        return;
    }
    if (seq > 1) {
        setErrorFlash();
        return;
    }
    if (checksum != (uint8_t)(msg_id ^ seq ^ brightness)) {
        setErrorFlash();
        return;
    }

    // --- Update LEDs ---
    // REF: always on
    setLed(0, 1);

    // D0-D4: msg_id bits (LSB first)
    setLed(1, (msg_id >> 0) & 1);  // D0
    setLed(2, (msg_id >> 1) & 1);  // D1
    setLed(3, (msg_id >> 2) & 1);  // D2
    setLed(4, (msg_id >> 3) & 1);  // D3
    setLed(5, (msg_id >> 4) & 1);  // D4

    // SEQ
    setLed(6, seq);

    // PAR: even parity of D0..D4 and SEQ
    uint8_t par = 0;
    for (int i = 1; i <= 6; i++) {
        par ^= led_state[i];
    }
    setLed(7, par);
}
