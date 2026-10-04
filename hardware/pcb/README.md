# Schematics

`eletect_x/` is the KiCad project for the field board: four sheets (geophone, LED and IR, sound and
LoRa, power) under one root sheet, with the same Arduino UNO Q drawn on each. `eletect_x_schematics.pdf`
is the full export and `erc_report.txt` the last ERC run.

The sheets and the field board are the same design. There are no known differences to track.

Pins used on the UNO Q match `device/mcu/src/config.h`:

| Sheet | Pins |
|---|---|
| Geophone | A4/PC1 SDA, A5/PC0 SCL (I2C3, `Wire2`) |
| LED and IR | D3/PB0 left wing, D6/PB1 right wing, D7/PB2 IR board |
| Sound and LoRa | D0/PB7 RX, D1/PB6 TX, D4/PA12 select, D11/PB15 amp enable |
