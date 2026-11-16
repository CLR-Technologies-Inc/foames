**Goal:** bring machine data from an Ignition gateway into FoaMES. FoaMES only reads; it never writes tags.

**You need:** admin access to the Ignition gateway, Machines in FoaMES with Source IDs, and the FoaMES Engineer role.

## Option A: Sparkplug B (preferred)

Use this when you have the Cirrus Link MQTT Transmission module. It reports by exception and tells FoaMES when a node goes offline.

1. In **Machine Data Settings**, fill in the MQTT broker (often Ignition's own MQTT Distributor) and tick **Sparkplug B Enabled**.
2. In MQTT Transmission, create a Transmitter whose tag folder holds **one subfolder per machine**, named like the machine's Source ID.
3. Inside each folder, name tags by the convention:

   ```
   press-1/
     state        (String)  "Running"
     good         (Int64)   120341
     scrap        (Int64)   871
     temperature  (Double)  72.5
   ```

   `state` becomes a State event, `good` and `scrap` become counts (send running totals), `alarm` an Alarm, `message` a Message, and any other numeric tag a Measurement. For tags you cannot rename, map them in **Node and Metric Map**.
4. Run the Sparkplug gateway under supervisor ([Run the gateways in production](How-to-Run-the-gateways-in-production)).

## Option B: OPC UA

1. Enable Ignition's OPC UA server and give it a user.
2. Map each tag in **Node and Metric Map** with source OPC UA, for example `ns=2;s=[default]Line1/Press1/GoodCount`.
3. Use **SignAndEncrypt** with a client certificate. After the first connection attempt, trust the certificate in Ignition under Config, OPC UA, Security, Server tab, **Quarantined Certificates**.
4. Run the OPC UA gateway. The default endpoint is `opc.tcp://<gateway host>:62541/discovery`.

## Option C: a gateway script

Use a Tag Change or scheduled gateway script that POSTs signed JSON to the webhook with `system.net.httpClient()`. This lets Ignition's scripting decide what counts as an event. A complete script is in [docs/vendors/ignition](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/ignition/README.md#webhook-from-a-gateway-script).

## Check

Watch the **Machine Event** list and the **Floor View**. With Sparkplug, disabling the transmitter should turn the machines grey (Unknown) within moments.
