FoaMES relies on the Frappe scheduler. Check it with `bench --site <site> scheduler status` and enable it with `bench --site <site> enable-scheduler`. Every adapter job returns at once unless that adapter is enabled in its settings. Run any job by hand with `bench --site <site> execute <dotted path>`.

| When | Job | What it does |
| --- | --- | --- |
| Every scheduler tick | `foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox.process_outbox` | Performs due ERPNext postings |
| Every scheduler tick | `foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox.process_outbox` | Sends due S/4HANA postings |
| Every scheduler tick | `foames.foames_adapters.doctype.insights_hub_outbox.insights_hub_outbox.process_outbox` | Sends due Insights Hub writes |
| Every scheduler tick | `foames.foames_adapters.doctype.mes_outbox.mes_outbox.process_outbox` | Sends due writes to MES Connections |
| Every 5 minutes | `foames.foames_mes.tasks.mark_stale_machines_unknown` | Marks a machine Unknown after **Mark Machine Unknown After** minutes of silence (15 by default) |
| Every 5 minutes | `foames.foames_mes.doctype.andon_call.andon_call.escalate_andon_calls` | Raises a suggestion for each andon call that missed a target |
| Every 10 minutes | `foames.foames_adapters.erpnext.rollup.roll_up_all` | Rolls machine counts up to ERPNext Job Cards |
| Every 10 minutes | `foames.foames_adapters.s4hana.rollup.roll_up_all` | Rolls machine counts up to S/4HANA confirmations |
| Every 10 minutes | `foames.foames_adapters.insights_hub.rollup.roll_up_all` | Rolls machine data up to Insights Hub time series |
| Hourly | `foames.foames_mes.tasks.run_suggestion_rules` | Runs the built-in and SPC suggestion rules over the last day |
| Hourly | `foames.foames_mes.tasks.check_maintenance_plans` | Reads each plan's meter, opens work orders, raises due suggestions |
| Daily | `foames.foames_mes.tasks.compute_daily_oee` | Creates OEE Periods for the previous day, per shift where a Shift Pattern is set |
| Daily | `foames.foames_kernel.tasks.refresh_external_references` | Re-checks External References that are Unverified or Missing |
| Daily | `foames.foames_mes.doctype.standard_operating_procedure.standard_operating_procedure.check_sops` | Makes approved SOPs effective, refreshes review status, raises review and training suggestions |

All jobs are idempotent: running one twice creates nothing twice.
