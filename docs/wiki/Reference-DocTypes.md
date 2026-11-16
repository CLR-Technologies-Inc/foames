Every DocType FoaMES installs on `main`, grouped by module, with its fields as they are defined in the app. Settings (single DocTypes) are on [[Reference: Settings|Reference-Settings]]. Child tables are listed under the DocType that holds them.

This page is generated from the DocType JSON files on `main`. When the two disagree, the code wins.

## FoaMES Kernel

### External Reference

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| ERP System | `erp_system` | Data | required |
| Reference Type | `reference_type` | Select | Item, Unit of Measure, Batch, Serial Number, Work Order, Operation, Location, Stock Movement, Job Card, Bill of Materials, Routing, Workstation, Asset; required |
| External ID | `external_id` | Data | required |
| Label | `label` | Data | read only |
| Status | `status` | Select | Unverified, Resolved, Missing; read only; default `Unverified` |
| Last Resolved On | `last_resolved_on` | Datetime | read only |
| Reference Key | `reference_key` | Data | read only; unique |

## FoaMES MES

### Agent Suggestion

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Series | `naming_series` | Select | SUG-.YYYY.-; default `SUG-.YYYY.-` |
| Title | `title` | Data | required |
| Category | `category` | Select | Yield, Downtime, Quality, Release, Machine Data, Maintenance, ERP, Andon, Other; required |
| Severity | `severity` | Select | Info, Warning, Critical; default `Warning` |
| Status | `status` | Select | Open, Accepted, Dismissed, Done; default `Open` |
| Agent | `agent` | Data |  |
| Reference DocType | `reference_doctype` | Link | → DocType |
| Reference Name | `reference_name` | Dynamic Link | → reference_doctype |
| Suggestion | `suggestion` | Text Editor | required |
| Evidence | `evidence` | JSON |  |
| Rule Key | `rule_key` | Data | unique |
| Resolution | `resolution` | Small Text |  |
| Resolved By | `resolved_by` | Link | → User; read only |
| Resolved On | `resolved_on` | Datetime | read only |

### Andon Call

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Series | `naming_series` | Select | ANDON-.YYYY.-; default `ANDON-.YYYY.-` |
| Machine | `machine` | Link | → Machine; required |
| Call Type | `call_type` | Link | → Andon Call Type; required |
| Note | `note` | Small Text |  |
| Status | `status` | Select | Open, Acknowledged, Resolved, Cancelled; default `Open` |
| Raised At | `raised_at` | Datetime | required; default `Now` |
| Raised By | `raised_by` | Link | → User; read only |
| Acknowledged At | `acknowledged_at` | Datetime | read only |
| Acknowledged By | `acknowledged_by` | Link | → User; read only |
| Response (min) | `response_minutes` | Float | read only |
| Resolved At | `resolved_at` | Datetime | read only |
| Resolved By | `resolved_by` | Link | → User; read only |
| Resolution (min) | `resolution_minutes` | Float | read only |
| Resolution | `resolution` | Small Text |  |
| Acknowledge Target Escalated | `ack_escalated` | Check | read only; default `0` |
| Resolve Target Escalated | `resolve_escalated` | Check | read only; default `0` |

### Andon Call Type

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Code | `code` | Data | required; unique |
| Title | `title` | Data |  |
| Disabled | `disabled` | Check | default `0` |
| Acknowledge Within (min) | `acknowledge_within_minutes` | Int | default `5` |
| Resolve Within (min) | `resolve_within_minutes` | Int | default `30` |
| Escalation Severity | `escalation_severity` | Select | Warning, Critical; default `Warning` |

### Downtime Reason

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Code | `code` | Data | required; unique |
| Title | `title` | Data |  |
| Category | `category` | Select | Planned, Unplanned, Changeover, Breakdown, No Material, No Operator, Quality, Other; default `Unplanned` |
| Counts As Planned Downtime | `counts_as_planned` | Check | default `0` |

### Downtime Record

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Series | `naming_series` | Select | DT-.YYYY.-; default `DT-.YYYY.-` |
| Machine | `machine` | Link | → Machine; required |
| Reason | `reason` | Link | → Downtime Reason |
| Status | `status` | Select | Open, Closed; read only; default `Open` |
| Source | `source` | Select | Automatic, Manual; default `Manual` |
| Start | `start_time` | Datetime | required |
| End | `end_time` | Datetime |  |
| Duration (min) | `duration_minutes` | Float | read only |
| Notes | `notes` | Small Text |  |

### Machine

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Code | `code` | Data | required; unique |
| Title | `title` | Data |  |
| Machine Type | `machine_type` | Data |  |
| Line | `line` | Data |  |
| Status | `status` | Select | Unknown, Running, Idle, Down, Setup; read only; default `Unknown` |
| Last Seen | `last_seen` | Datetime | read only |
| Last Count At | `last_count_at` | Datetime | read only |
| Disabled | `disabled` | Check | default `0` |
| Ideal Cycle Time (s) | `ideal_cycle_seconds` | Float |  |
| Shift Start | `shift_start` | Time |  |
| Scheduled Minutes Per Day | `scheduled_minutes_per_day` | Float | default `480` |
| Shift Pattern | `shift_pattern` | Link | → Shift Pattern |
| Equipment Complexity Level (ECL) | `ecl` | Select | empty (not rated), 1, 2, 3, 4, 5 |
| ECL Equipment Class | `ecl_class` | Data | class id from the public ECL list, lower-case kebab-case |
| ECL Rationale | `ecl_rationale` | Small Text |  |
| Current Job Reference | `current_job_reference` | Link | → External Reference |
| Current Job Since | `current_job_since` | Datetime | read only |
| Source ID | `source_id` | Data | unique |
| Counter Rollover | `counter_rollover` | Int |  |
| ERP Workstation Reference | `workstation_reference` | Link | → External Reference |
| ERP Location Reference | `location_reference` | Link | → External Reference |
| ERP Asset Reference | `asset_reference` | Link | → External Reference |

### Machine Event

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Machine | `machine` | Link | → Machine; required |
| Event Type | `event_type` | Select | State, Count, Measurement, Alarm, Message; required |
| Timestamp | `timestamp` | Datetime | required |
| Source | `source` | Select | Webhook, MQTT, OPC UA, Manual, System; default `Manual` |
| State | `state` | Select | Unknown, Running, Idle, Down, Setup |
| Counter | `counter_name` | Data |  |
| Counter Value | `counter_value` | Float |  |
| Delta | `delta` | Float | read only |
| Measurement | `measurement_name` | Data |  |
| Value | `value` | Float |  |
| Text | `text` | Data |  |
| Processed | `processed` | Check | read only; default `0` |
| Processing Note | `processing_note` | Small Text | read only |
| Raw Payload | `payload` | JSON |  |
| Event Key | `event_key` | Data | unique |

### Machine Node Map (child table)

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Machine | `machine` | Link | → Machine; required |
| Source | `source` | Select | OPC UA, Sparkplug B; required; default `OPC UA` |
| Node ID or Metric Path | `node_id` | Data | required |
| Event Type | `event_type` | Select | State, Count, Measurement, Alarm, Message; required |
| Counter / Measurement Name | `name_or_counter` | Data |  |
| State Map | `state_map` | Small Text |  |

### Maintenance Plan

A preventive maintenance task for one machine, due by calendar, run hours or counts

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Series | `naming_series` | Select | MPL-.#####; default `MPL-.#####` |
| Title | `title` | Data | required |
| Machine | `machine` | Link | → Machine; required |
| Disabled | `disabled` | Check | default `0` |
| Status | `status` | Select | OK, Due Soon, Due, Overdue; read only; default `OK` |
| Open Work Order | `open_work_order` | Link | → Maintenance Work Order; read only |
| Trigger | `trigger_type` | Select | Calendar, Run Hours, Count; required; default `Calendar` |
| Interval | `interval` | Float | required |
| Counter | `counter_name` | Data |  |
| Due Soon At (%) | `warn_percent` | Percent | default `90` |
| Overdue After (%) | `grace_percent` | Percent | default `10` |
| Create Work Order When Due | `auto_create_work_order` | Check | default `0` |
| Last Service | `last_done_on` | Datetime |  |
| Last Work Order | `last_work_order` | Link | → Maintenance Work Order; read only |
| Meter Read At | `last_checked` | Datetime | read only |
| Used | `used` | Float | read only |
| Used (%) | `percent_used` | Percent | read only |
| Remaining | `remaining` | Float | read only |
| Due On | `due_on` | Datetime | read only |
| Downtime Reason | `downtime_reason` | Link | → Downtime Reason |
| Estimated Minutes | `estimated_minutes` | Float |  |
| Instructions | `instructions` | Text Editor |  |

### Maintenance Work Order

One service of a Maintenance Plan; completing it restarts the plan's meter

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Series | `naming_series` | Select | MWO-.YYYY.-; default `MWO-.YYYY.-` |
| Maintenance Plan | `maintenance_plan` | Link | → Maintenance Plan; required |
| Title | `title` | Data |  |
| Machine | `machine` | Link | → Machine; read only |
| Status | `status` | Select | Open, In Progress, Completed, Cancelled; default `Open` |
| Assigned To | `assigned_to` | Link | → User |
| Due On | `due_on` | Datetime |  |
| Plan Status | `plan_status_at_raise` | Data | read only |
| Used Since Service | `meter_at_raise` | Float | read only |
| Started On | `started_on` | Datetime |  |
| Completed On | `completed_on` | Datetime |  |
| Completed By | `completed_by` | Link | → User; read only |
| Actual Minutes | `actual_minutes` | Float | read only |
| Downtime Record | `downtime_record` | Link | → Downtime Record; read only |
| Instructions | `instructions` | Text Editor |  |
| Findings | `findings` | Small Text |  |

### OEE Period

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Machine | `machine` | Link | → Machine; required |
| Shift | `shift` | Data |  |
| From | `from_time` | Datetime | required |
| To | `to_time` | Datetime | required |
| Planned Minutes | `planned_minutes` | Float | required |
| Ideal Cycle Time (s) | `ideal_cycle_seconds` | Float |  |
| Run Minutes | `run_minutes` | Float | read only |
| Planned Downtime (min) | `planned_downtime_minutes` | Float | read only |
| Unplanned Downtime (min) | `unplanned_downtime_minutes` | Float | read only |
| Unknown Minutes | `unknown_minutes` | Float | read only |
| Signal Coverage | `coverage` | Percent | read only |
| Good Count | `good_count` | Float | read only |
| Scrap Count | `scrap_count` | Float | read only |
| Availability | `availability` | Percent | read only |
| Performance | `performance` | Percent | read only |
| Quality | `quality` | Percent | read only |
| OEE | `oee` | Percent | read only |

### Shift Pattern

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Pattern Name | `pattern_name` | Data | required; unique |
| Description | `description` | Small Text |  |
| Shifts | `shifts` | Table | → Shift Pattern Shift; required |
| Non-Working Days | `holidays` | Table | → Shift Pattern Holiday |

### Shift Pattern Holiday (child table)

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Date | `holiday_date` | Date | required |
| Description | `description` | Data |  |

### Shift Pattern Shift (child table)

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Shift | `shift_name` | Data | required |
| Start | `start_time` | Time | required |
| Minutes | `duration_minutes` | Float | required; default `480` |
| Monday | `monday` | Check | default `1` |
| Tuesday | `tuesday` | Check | default `1` |
| Wednesday | `wednesday` | Check | default `1` |
| Thursday | `thursday` | Check | default `1` |
| Friday | `friday` | Check | default `1` |
| Saturday | `saturday` | Check | default `0` |
| Sunday | `sunday` | Check | default `0` |

### SOP Acknowledgement

A person's record that they read, or were trained on, one SOP revision

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| SOP Revision | `sop` | Link | → Standard Operating Procedure; required |
| SOP Code | `sop_code` | Data | read only |
| Revision | `revision` | Int | read only |
| User | `user` | Link | → User; required |
| Method | `method` | Select | Read and Understood, Trained, Trained and Assessed; required; default `Read and Understood` |
| Acknowledged On | `acknowledged_on` | Datetime | read only |
| Recorded By | `recorded_by` | Link | → User; read only |
| Note | `note` | Small Text |  |

### SOP Applicability (child table)

Where an SOP applies: a machine, every machine on a line, or a process step in the ERP

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Machine | `machine` | Link | → Machine |
| Line | `line` | Data |  |
| Process Reference | `external_reference` | Link | → External Reference |
| Note | `note` | Data |  |

### SOP Approval (child table)

One sign-off an SOP revision needs: a role, and who signed for it and when

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Role | `role` | Link | → Role; required |
| Meaning | `meaning` | Select | Reviewed, Approved, Quality Approved; required; default `Approved` |
| Signed By | `signed_by` | Link | → User; read only |
| Signed On | `signed_on` | Datetime | read only |
| Comment | `comment` | Small Text | read only |

### SOP Training Role (child table)

A role whose users must acknowledge an SOP

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Role | `role` | Link | → Role; required |

### Standard Operating Procedure

One revision of a controlled standard operating procedure

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| SOP Code | `sop_code` | Data | required |
| Revision | `revision` | Int | read only |
| Title | `title` | Data | required |
| Category | `category` | Select | Operations, Quality, Safety, Maintenance, Engineering, Other; default `Operations` |
| Status | `status` | Select | Draft, In Review, Approved, Effective, Superseded, Obsolete; read only; default `Draft` |
| Document Owner | `document_owner` | Link | → User |
| Prepared By | `prepared_by` | Link | → User; read only |
| Supersedes | `supersedes` | Link | → Standard Operating Procedure; read only |
| Superseded By | `superseded_by` | Link | → Standard Operating Procedure; read only |
| Purpose | `purpose` | Small Text |  |
| Scope | `scope` | Small Text |  |
| Responsibilities | `responsibilities` | Small Text |  |
| Procedure | `procedure` | Text Editor | required |
| References | `references` | Small Text |  |
| Controlled Copy | `attachment` | Attach |  |
| Change Summary | `change_summary` | Small Text |  |
| Applies To | `applies_to` | Table | → SOP Applicability |
| Approvals | `approvals` | Table | → SOP Approval |
| Effective On | `effective_on` | Date |  |
| Review Every (Months) | `review_interval_months` | Int | default `12` |
| Last Reviewed On | `last_reviewed_on` | Date | read only |
| Next Review On | `next_review_on` | Date | read only |
| Review Status | `review_status` | Select | Current, Review Due Soon, Review Overdue; read only |
| Retired On | `retired_on` | Date | read only |
| Retire Reason | `retire_reason` | Small Text | read only |
| Requires Acknowledgement | `requires_acknowledgement` | Check | default `1` |
| Training Roles | `training_roles` | Table MultiSelect | → SOP Training Role |
| Acknowledge Within (Days) | `acknowledge_within_days` | Int | default `14` |

## FoaMES Process Mining

### Event Log Source

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Source Name | `source_name` | Data | required; unique |
| Enabled | `enabled` | Check | default `1` |
| Source DocType | `source_doctype` | Data | required |
| Case Field | `case_field` | Data | required |
| Activity Field | `activity_field` | Data |  |
| Fixed Activity | `fixed_activity` | Data |  |
| Timestamp Field | `timestamp_field` | Data | required |
| End Timestamp Field | `end_timestamp_field` | Data |  |
| Resource Field | `resource_field` | Data |  |
| Filters | `filters` | Small Text |  |
| Attribute Fields | `attribute_fields` | Data |  |
| Object Fields | `object_fields` | Data |  |
| Description | `description` | Small Text |  |

### Process Event Log

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Title | `title` | Data | required |
| Status | `status` | Select | Draft, Extracted, Failed; read only; default `Draft` |
| From | `from_time` | Datetime |  |
| To | `to_time` | Datetime |  |
| Include built-in machine and downtime events | `include_built_in` | Check | default `1` |
| Event Log Sources | `sources` | Table | → Process Event Log Source |
| Events | `event_count` | Int | read only |
| Cases | `case_count` | Int | read only |
| Variants | `variant_count` | Int | read only |
| Activities | `activity_count` | Int | read only |
| Extracted On | `extracted_on` | Datetime | read only |
| Note | `extraction_note` | Small Text | read only |
| Events (JSON) | `events_json` | JSON | read only |

### Process Event Log Source (child table)

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Event Log Source | `source` | Link | → Event Log Source; required |

## FoaMES Adapters

### ERPNext Outbox

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Operation | `operation` | Select | Material Transfer for Manufacture, Manufacture, Material Consumption for Manufacture, Job Card Time Log, Job Card Production Log, Work Order Status, Workstation Status, Downtime Entry, Asset Repair, Quality Inspection; required |
| Status | `status` | Select | Queued, Sending, Retry, Posted, Failed, Cancelled; read only; default `Queued` |
| Sequence Group | `sequence_group` | Data |  |
| Idempotency Key | `idempotency_key` | Data | required; unique |
| ERPNext Document Type | `erp_doctype` | Data | read only |
| ERPNext Document | `erp_document` | Data | read only |
| External Reference | `external_reference` | Link | → External Reference; read only |
| Source Type | `reference_doctype` | Link | → DocType |
| Source | `reference_name` | Dynamic Link | → reference_doctype |
| Attempts | `attempts` | Int | read only; default `0` |
| Next Attempt | `next_attempt_at` | Datetime | read only |
| Last Attempt | `last_attempt_at` | Datetime | read only |
| Posted On | `posted_on` | Datetime | read only |
| Last Error | `last_error` | Small Text | read only |
| Error Details | `error_details` | Code | read only |
| Payload | `payload` | Code | required |
| Response | `response` | Code | read only |

### Insights Hub Entity Mapping (child table)

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Reference Type | `reference_type` | Select | Item, Unit of Measure, Batch, Serial Number, Work Order, Operation, Location, Stock Movement, Job Card, Bill of Materials, Routing, Workstation, Asset; required |
| Service | `service` | Data | required |
| Resource | `resource` | Data | required |
| Lookup | `lookup` | Select | Path, Filter; required; default `Path` |
| Key Fields | `key_fields` | Data | required |
| Label Field | `label_field` | Data |  |

### Insights Hub Outbox

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Operation | `operation` | Select | Time Series Write, Event; required |
| Status | `status` | Select | Queued, Sending, Retry, Unknown, Posted, Failed, Cancelled; read only; default `Queued` |
| Sequence Group | `sequence_group` | Data |  |
| Idempotency Key | `idempotency_key` | Data | required; unique |
| Insights Hub Record | `hub_document` | Data | read only |
| Source Type | `reference_doctype` | Link | → DocType |
| Source | `reference_name` | Dynamic Link | → reference_doctype |
| Attempts | `attempts` | Int | read only; default `0` |
| Next Attempt | `next_attempt_at` | Datetime | read only |
| Last Attempt | `last_attempt_at` | Datetime | read only |
| Posted On | `posted_on` | Datetime | read only |
| Last Error | `last_error` | Small Text | read only |
| Error Details | `error_details` | Code | read only |
| Payload | `payload` | Code | required |
| Sent Payload | `sent_payload` | Code | read only |
| Response | `response` | Code | read only |

### MES Connection

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Adapter | `adapter` | Select | PLEX, FTPC, SAP_DMC, APRISO, AVEVA_MES, CMF_MES, TULIP, FACTORYLOGIX, PASX, PROFICY; required |
| Enabled | `enabled` | Check | default `0` |
| API Documentation | `documentation_url` | Data | read only |
| Base URL | `base_url` | Data |  |
| Site / Plant / Tenant | `site` | Data |  |
| Test Path | `test_path` | Data |  |
| Timeout (seconds) | `timeout` | Int | default `30` |
| CA Bundle Path | `ca_bundle` | Data |  |
| Extra Headers | `extra_headers` | Small Text |  |
| Method | `auth_method` | Select | None, Basic, Bearer Token, API Key Header, OAuth 2.0 Client Credentials; required; default `Basic` |
| Username | `username` | Data |  |
| Password | `password` | Password |  |
| Token | `token` | Password |  |
| API Key | `api_key` | Password |  |
| API Key Header | `api_key_header` | Data |  |
| Token URL | `token_url` | Data |  |
| Client ID | `client_id` | Data |  |
| Client Secret | `client_secret` | Password |  |
| Scope | `scope` | Data |  |
| Entity Mappings | `entity_mappings` | Table | → MES Entity Mapping |
| Pause Outbox | `outbox_paused` | Check | default `0` |
| Notes | `profile_notes` | Small Text | read only |

### MES Entity Mapping (child table)

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Reference Type | `reference_type` | Select | Item, Unit of Measure, Batch, Serial Number, Work Order, Operation, Location, Stock Movement, Job Card, Bill of Materials, Routing, Workstation, Asset; required |
| Path | `path` | Data | required |
| Lookup | `lookup` | Select | Path, Query, OData, JSON Filter; required; default `Query` |
| Key Fields | `key_fields` | Data | required |
| Label Field | `label_field` | Data |  |
| Extra Query | `extra_query` | Data |  |

### MES Outbox

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Connection | `connection` | Link | → MES Connection; required |
| Operation | `operation` | Data | required |
| Status | `status` | Select | Queued, Sending, Retry, Unknown, Posted, Failed, Cancelled; read only; default `Queued` |
| Needs Check | `needs_check` | Check | read only; default `0` |
| Sequence Group | `sequence_group` | Data |  |
| Idempotency Key | `idempotency_key` | Data | required; unique |
| MES Record | `mes_document` | Data | read only |
| Source Type | `reference_doctype` | Link | → DocType |
| Source | `reference_name` | Dynamic Link | → reference_doctype |
| Attempts | `attempts` | Int | read only; default `0` |
| Next Attempt | `next_attempt_at` | Datetime | read only |
| Last Attempt | `last_attempt_at` | Datetime | read only |
| Posted On | `posted_on` | Datetime | read only |
| Last Error | `last_error` | Small Text | read only |
| Error Details | `error_details` | Code | read only |
| Payload | `payload` | Code | required |
| Sent Payload | `sent_payload` | Code | read only |
| Response | `response` | Code | read only |

### S4HANA Entity Mapping (child table)

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Reference Type | `reference_type` | Select | Item, Unit of Measure, Batch, Serial Number, Work Order, Operation, Location, Stock Movement, Asset; required |
| OData Service | `service` | Data | required |
| Entity Set | `entity_set` | Data | required |
| Key Fields | `key_fields` | Data | required |
| Optional Keys | `optional_keys` | Data |  |
| Label Field | `label_field` | Data |  |

### S4HANA Inbound IDoc

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| IDoc Number | `idoc_number` | Data | required; read only |
| Message Type | `message_type` | Data | read only |
| Basic Type | `idoc_type` | Data | read only |
| Sender Partner | `sender` | Data | read only |
| Status | `status` | Select | Received, Processed, Failed; read only; default `Received` |
| External Reference | `external_reference` | Link | → External Reference; read only |
| Error | `error` | Small Text | read only |
| Summary | `summary` | Code | read only |
| Control Record | `control` | Code | read only |
| Segments | `segments` | Code | read only |

### S4HANA Outbox

| Field | Fieldname | Type | Notes |
| --- | --- | --- | --- |
| Operation | `operation` | Select | Production Order Confirmation, Process Order Confirmation, Goods Movement, Confirmation Cancellation, Process Confirmation Cancellation, Material Document Reversal; required |
| Status | `status` | Select | Queued, Sending, Retry, Unknown, Posted, Failed, Cancelled; read only; default `Queued` |
| Sequence Group | `sequence_group` | Data |  |
| Idempotency Key | `idempotency_key` | Data | required; unique |
| S/4HANA Document | `sap_document` | Data | read only |
| External Reference | `external_reference` | Link | → External Reference; read only |
| Source Type | `reference_doctype` | Link | → DocType |
| Source | `reference_name` | Dynamic Link | → reference_doctype |
| Attempts | `attempts` | Int | read only; default `0` |
| Next Attempt | `next_attempt_at` | Datetime | read only |
| Last Attempt | `last_attempt_at` | Datetime | read only |
| Posted On | `posted_on` | Datetime | read only |
| Last Error | `last_error` | Small Text | read only |
| Error Details | `error_details` | Code | read only |
| Payload | `payload` | Code | required |
| Sent Payload | `sent_payload` | Code | read only |
| Response | `response` | Code | read only |
