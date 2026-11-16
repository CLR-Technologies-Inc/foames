The single DocTypes (one record per site) that configure FoaMES, with every field. All of them are edited in the desk by a System Manager. Which settings you need for a task is in the matching how-to guide.

This page is generated from the DocType JSON files on `main`. When the two disagree, the code wins.

## FoaMES Kernel

### FoaMES Settings

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Default ERP System | `default_erp_system` | Data |  |
| Skip Resolving References on Save | `skip_resolution_on_save` | Check | default `0` |

## FoaMES MES

### Machine Data Settings

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Webhook Secret | `webhook_secret` | Password |  |
| Signature Tolerance (s) | `signature_tolerance_seconds` | Int | default `300` |
| MQTT Enabled | `mqtt_enabled` | Check | default `0` |
| Broker Host | `mqtt_broker` | Data |  |
| Port | `mqtt_port` | Int | default `1883` |
| Use TLS | `mqtt_tls` | Check | default `0` |
| Username | `mqtt_username` | Data |  |
| Password | `mqtt_password` | Password |  |
| Topic Prefix | `mqtt_topic_prefix` | Data | default `foames` |
| Sparkplug B Enabled | `sparkplug_enabled` | Check | default `0` |
| Group ID | `sparkplug_group_id` | Data |  |
| OPC UA Enabled | `opcua_enabled` | Check | default `0` |
| Endpoint URL | `opcua_endpoint` | Data |  |
| Poll Interval (s) | `opcua_poll_seconds` | Int | default `5` |
| Username | `opcua_username` | Data |  |
| Password | `opcua_password` | Password |  |
| Node and Metric Map | `node_map` | Table | → Machine Node Map |
| Message Security Mode | `opcua_security_mode` | Select | None, Sign, SignAndEncrypt; default `None` |
| Security Policy | `opcua_security_policy` | Select | Basic256Sha256, Aes128_Sha256_RsaOaep, Aes256_Sha256_RsaPss; default `Basic256Sha256` |
| Client Application URI | `opcua_application_uri` | Data |  |
| Client Certificate | `opcua_client_certificate` | Attach |  |
| Client Private Key | `opcua_private_key` | Attach |  |
| Private Key Passphrase | `opcua_private_key_password` | Password |  |
| Server Certificate | `opcua_server_certificate` | Attach |  |
| Trusted Certificates | `opcua_trusted_certificates` | Attach |  |
| Mark Machine Unknown After (min) | `stale_after_minutes` | Int | default `15` |
| SPC Suggestions Enabled | `spc_enabled` | Check | default `1` |
| Run Rules | `spc_rule_set` | Select | Nelson, Western Electric; default `Nelson` |
| X-bar R Subgroup Size | `spc_subgroup_size` | Int | default `0` |
| Baseline Window (days) | `spc_baseline_days` | Int | default `7` |
| Judge Readings From the Last (hours) | `spc_recent_hours` | Int | default `2` |
| Minimum Baseline Readings | `spc_min_baseline_points` | Int | default `20` |

## FoaMES Adapters

### ERPNext Adapter Settings

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Enable Postings to ERPNext | `enable_postings` | Check | default `0` |
| Pause the Outbox | `outbox_paused` | Check | default `0` |
| Submit Job Cards When Complete | `submit_job_cards_when_complete` | Check | default `0` |
| Roll Up Machine Counts to Job Cards | `roll_up_counts_to_job_cards` | Check | default `0` |
| Inspect Job Cards from Machine Measurements | `inspect_job_cards_from_measurements` | Check | default `0` |
| Wait for Late Measurements (minutes) | `inspection_delay_minutes` | Int | default `5` |
| Show Job Cards on the Floor | `show_job_cards_on_floor` | Check | default `1` |
| Follow Job Cards Started in ERPNext | `follow_job_cards_started_in_erpnext` | Check | default `0` |
| Look Ahead (days) | `floor_lookahead_days` | Int | default `2` |
| Show Machine State on Workstations | `sync_machine_state_to_workstations` | Check | default `0` |
| Post Downtime to ERPNext | `post_downtime_to_erpnext` | Check | default `0` |
| Downtime Operator (Employee ID) | `downtime_operator` | Data |  |
| Post Maintenance Work Orders to ERPNext | `post_maintenance_to_erpnext` | Check | default `0` |
| Submit Asset Repairs When Complete | `submit_asset_repairs` | Check | default `0` |
| Refresh Unresolved References Daily | `refresh_references_daily` | Check | default `1` |

### Insights Hub Settings

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Enabled | `enabled` | Check | default `0` |
| Gateway URL | `gateway_url` | Data |  |
| Tenant | `tenant` | Data |  |
| Timeout (seconds) | `timeout` | Int | default `30` |
| CA Bundle Path | `ca_bundle` | Data |  |
| Method | `auth_method` | Select | Technical Token Manager, Service Credentials; default `Technical Token Manager` |
| Client ID | `client_id` | Data |  |
| Client Secret | `client_secret` | Password |  |
| Application Name | `app_name` | Data |  |
| Application Version | `app_version` | Data | default `1.0.0` |
| Host Tenant | `host_tenant` | Data |  |
| User Tenant | `user_tenant` | Data |  |
| Credentials Header Scheme | `token_manager_scheme` | Select | Basic, Bearer; default `Basic` |
| Token URL | `token_url` | Data |  |
| Entity Mappings | `entity_mappings` | Table | → Insights Hub Entity Mapping |
| Pause Outbox | `outbox_paused` | Check | default `0` |
| Send Machine Production as Time Series | `send_machine_data` | Check | default `0` |
| Aspect | `property_set` | Data | default `FoaMESProduction` |
| Send State Changes as Events | `send_state_events` | Check | default `0` |
| Event Type ID | `event_type_id` | Data |  |
| Good Count Variable | `good_variable` | Data | default `goodCount` |
| Scrap Count Variable | `scrap_variable` | Data | default `scrapCount` |
| Running Minutes Variable | `run_minutes_variable` | Data | default `runMinutes` |
| Window Minutes Variable | `window_minutes_variable` | Data | default `windowMinutes` |
| Job Variable | `job_variable` | Data | default `job` |
| State Variable | `state_variable` | Data | default `state` |

### S4HANA Settings

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Enabled | `enabled` | Check | default `0` |
| Base URL | `base_url` | Data |  |
| SAP Client | `sap_client` | Data |  |
| Language | `language` | Data | default `EN` |
| Timeout (seconds) | `timeout` | Int | default `30` |
| CA Bundle Path | `ca_bundle` | Data |  |
| Method | `auth_method` | Select | Basic, OAuth 2.0 Client Credentials; default `Basic` |
| Username | `username` | Data |  |
| Password | `password` | Password |  |
| Token URL | `token_url` | Data |  |
| Client ID | `client_id` | Data |  |
| Client Secret | `client_secret` | Password |  |
| Scope | `scope` | Data |  |
| Entity Mappings | `entity_mappings` | Table | → S4HANA Entity Mapping |
| Pause Outbox | `outbox_paused` | Check | default `0` |
| Roll Up Machine Counts to Confirmations | `roll_up_counts_to_confirmations` | Check | default `0` |
| Confirmation Unit | `confirmation_unit` | Data |  |
| Jobs Are Process Orders | `confirm_process_orders` | Check | default `0` |
| Machine Time Activity Position | `machine_time_activity_position` | Int | default `0` |
| Machine Time Unit | `machine_time_unit` | Select | MIN, H; default `MIN` |
| Confirm Without Goods Movements | `confirm_without_goods_movements` | Check | default `0` |
