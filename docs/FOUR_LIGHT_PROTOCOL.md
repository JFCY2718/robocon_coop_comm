# Four-data-light cooperation protocol

## Optical layout

```text
bit0 D0   bit1 D1   bit2 D2   bit3 D3   bit4 REF   bit5 PAR
```

The data lights carry a persistent state ID from 0 through 15. REF is on for
every valid state. PAR equals `D0 XOR D1 XOR D2 XOR D3`, producing even parity
across the four data lights and PAR. The all-off pattern is reserved for
power loss, watchdog timeout, or a disabled Beacon.

Golden masks are stored in `docs/four_light_protocol_vectors.json` and checked
by the R1, vision, and R2 test suites.

## R1 to Beacon STM32 UART V2

Command, six bytes:

```text
BD 02 state_id counter brightness crc8
```

ACK, six bytes:

```text
BE 02 state_id counter status crc8
```

CRC is CRC-8/ATM with polynomial `0x07`, initial value `0x00`, over bytes 0
through 4. Status values are 0 OK, 1 bad version, 2 bad state, and 3 bad CRC.
R1 sends every 50 ms. Beacon turns every light off after 300 ms without a
valid V2 command. R1 treats the link as offline after 300 ms without a matching
OK ACK.

The legacy `AA 55` STM32 frame, the Rscontrol2 host `0xBC` frame, and the old
Rscontrol2 `0xAA/0xBB/0xAB` frames remain unchanged.

## Safety boundary

R1 sends a guarded mission state, never an operator-selected lamp mask. R2
treats the decoded value as a persistent state cue, validates REF/parity,
confidence and freshness, and then applies local sensor guards. Vision output
does not drive motors or actuators directly.
