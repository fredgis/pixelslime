constexpr int ButtonLeftPin = 4;
constexpr int ButtonOpenPin = 5;
constexpr int ButtonRightPin = 6;

void setup() {
  Serial.begin(115200);

  pinMode(ButtonLeftPin, INPUT_PULLUP);
  pinMode(ButtonOpenPin, INPUT_PULLUP);
  pinMode(ButtonRightPin, INPUT_PULLUP);
}

void loop() {
  if (digitalRead(ButtonLeftPin) == LOW) {
    Serial.println("LEFT");
    delay(180);
  }

  if (digitalRead(ButtonOpenPin) == LOW) {
    Serial.println("OPEN");
    delay(180);
  }

  if (digitalRead(ButtonRightPin) == LOW) {
    Serial.println("RIGHT");
    delay(180);
  }
}
