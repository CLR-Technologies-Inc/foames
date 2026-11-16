# foames-bms-gateway

Read-only gateway from building controllers and meters to FoaMES building points: BACnet/IP (ReadProperty, with optional status flags as reading quality) and Modbus TCP (function codes 1 to 4: coils, discrete inputs, input and holding registers, decoded as 16, 32 or 64-bit integers or floats with any word order). It posts each value to the signed readings webhook, where FoaMES checks it against the point's alarm limits. Standard library only.

The guide, with the point model, the alarm rules and utility consumption, is [docs/building-management.md](../../docs/building-management.md).

```bash
pip install .
export FOAMES_WEBHOOK_SECRET=...
python -m foames_bms_gateway check --config examples/bms.json
python -m foames_bms_gateway read  --config examples/bms.json
python -m foames_bms_gateway poll  --config examples/bms.json --site https://foames.example.com --interval 60
python -m unittest discover -s tests -v
```

The gateway never writes: it has no WriteProperty, no priority-array command and no Modbus write function code, and a test checks the package for them. Points behind another BACnet network take the router's `dnet` and the device's `dadr`. Values already collected by a historian or a SCADA platform can be posted to the same webhook by any client; give the Building Point the source's tag as its id. (The [historian bridge](../historian/README.md) feeds machine events, not building points.)

Licensed under the Apache License, Version 2.0, like FoaMES. It is written from the published protocol standards (ANSI/ASHRAE 135 for BACnet, the Modbus Application Protocol and Modbus TCP specifications) and contains no vendor code or SDK.
