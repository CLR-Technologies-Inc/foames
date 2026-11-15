**Goal:** keep the MQTT, Sparkplug B or OPC UA gateway running on a production bench, restarted when it fails.

**You need:** shell access to the bench host, and the gateway path already set up in **Machine Data Settings** ([Send machine data](How-to-Send-machine-data)). The signed webhook needs none of this; it is served by the normal web workers.

1. Install the gateway's package into the bench's own Python:

   ```bash
   cd /home/frappe/frappe-bench
   ./env/bin/pip install paho-mqtt     # MQTT and Sparkplug B
   ./env/bin/pip install asyncua       # OPC UA
   ```

2. Add a supervisor program per gateway to the bench's supervisor configuration (usually `config/supervisor.conf`), in the bench's group so `bench restart` covers it:

   ```ini
   [program:frappe-bench-foames-sparkplug]
   command=/usr/local/bin/bench --site site1.local execute foames.foames_mes.gateway.sparkplug.run
   directory=/home/frappe/frappe-bench
   user=frappe
   autostart=true
   autorestart=true
   startretries=10
   stdout_logfile=/home/frappe/frappe-bench/logs/foames-sparkplug.log
   stderr_logfile=/home/frappe/frappe-bench/logs/foames-sparkplug.error.log
   ```

   Adjust the `bench` path (`which bench`), the directory and the site.

3. Load it: `sudo supervisorctl reread && sudo supervisorctl update`.

A systemd unit with the same command, `WorkingDirectory` and `Restart=always` works the same way.

## Things to know

- Run **one gateway process per site**. A gateway serves only the site named in its command.
- Each gateway reads Machine Data Settings **once at start**. Restart it after changing the broker, endpoint, Sparkplug group, node map or certificates.
- A gateway exits with a message when its package is missing or its path is disabled, so check the error log if it keeps restarting.
- On Frappe Cloud or another hosted bench where you cannot run long processes, run a small bridge near the broker or OPC UA server that posts to the signed webhook instead.
