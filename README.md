# Shipment Tracking

Shipment Tracking is a plug-and-play Frappe app that integrates **Shipkia shipment synchronization and tracking** directly inside ERPNext.

It enables ERPNext users to automatically create, sync, and monitor shipment records from **Sales Invoices** while maintaining shipment visibility across related healthcare and billing documents.

---

## Features

- Automatically create **shipment records from Sales Invoices**
- Sync shipment information from **Shipkia API**
- Store and display full **shipment timeline events**
- Show **shipment summary directly on Sales Invoice**
- Mirror shipment details to **Patient Encounter**
- Add **tracking and shipment action buttons** on Sales Invoice
- Automatically display shipment fields only for **online encounters**
- Maintain real-time shipment visibility inside **ERPNext**

## WhatsApp notification engine

Shipment Tracking Settings provides an explicit choice between:

- `Legacy Shipment Tracking`
- `Patient Notification Hub`

Existing sites default to the legacy engine. Before switching, enable Patient Notification Hub and review
its Sales Invoice Generated, Order Picked Up, and Out for Delivery rules. Once the hub is selected, legacy
notification creation and retry jobs stop; existing legacy audit records remain available for history.

---

## Requirements

- **Frappe Framework** v15+
- **ERPNext** v15+
- **Python** 3.10+
- **Bench CLI**

---

## Installation

Install the app using the **Bench CLI**.

```bash
cd $PATH_TO_YOUR_BENCH

bench get-app https://github.com/YOUR_GITHUB_USERNAME/shipment_tracking.git

bench --site <your-site-name> install-app shipment_tracking

bench --site <your-site-name> migrate

bench build

bench restart
```

---

## License

MIT


### Shipkia accounts and V2 order routing

Shipment Tracking Settings selects one default Shipkia Account for new orders.
The invoice confirmation shows the account and payment summary. Legacy entry
points remain under `shipment_tracking.api.order`; the invoice button calls
`shipment_tracking.api.dispatch`. New OMS has an independent adapter under
`shipment_tracking.api.v2.order`, with no Legacy or product API dependencies.
Shipkia must resolve/create products from the supplied order product details.

Configure credentials, endpoints, pickup address, channel and parcel defaults on
each account. Existing global Legacy configuration is retained as rollback data,
but active provider operations read the account. Migration does not overwrite
already migrated account settings or change the default selection.

Before enabling V2 order sending, verify its server-managed product behavior,
JSON request format, rupee amounts, parcel units, order payload and response ID path with Shipkia,
then enable **V2 Contract Verified**. No live order is sent by migration.

New OMS order creation, order-details reconciliation, tracking, and secured status
webhooks are implemented. Manual tracking first checks Shipkia and compares the
normalized provider state with ERPNext. Matching data is reported as up to date;
differences require explicit confirmation before they are applied. Newer terminal
order states such as Cancelled take precedence over older tracking timeline events.
New OMS support remains disabled until its support API contract is verified.

Every shipment/log/ticket retains its account. Replacements require a reason,
keep the original account and create a separate shipment. Old callbacks cannot
replace the invoice's current shipment summary. Switching the default never
resends historical orders. Unassigned ownership and duplicate historical
identities require review; migration preserves them rather than guessing.

A timeout, server error or missing response ID leaves an **Uncertain** attempt;
**Running** and **Uncertain** attempts block another create across both accounts.
System Managers can open the sync log and choose **Reconcile order attempt**
after checking Shipkia. **Created** links the verified external order without a
provider request; **Not created** permits a later manual retry. Do not resolve an
attempt until the original operation has completed and the provider outcome is
known. There is no automatic retry or account fallback.

To use the backup provider, select **Legacy** as the default account and save.
Keep existing account records and credentials: historical operations use their
saved account. Reverting source code alone would lose V2 routing; take a full
backup before any schema/code rollback.

## Operations and diagnostics

System Managers can call shipment_tracking.api.health.get_operational_health to
obtain a read-only summary of shipment counts by account, Sync Log status counts,
unresolved order attempts, and duplicate historical account/order identities. The
endpoint returns counts only and does not expose credentials, request payloads,
addresses, or patient data.

Shipment Tracking Sync Log is the audit journal for provider requests and webhooks.
Running and Uncertain Create Order attempts must be reconciled before another order
can be sent. Successful tracking checks are retained for audit; define and review a
site-specific retention policy before deleting historical logs.

Database indexes support account/order ownership lookups, active shipment queries,
and operational log filtering. Migrations add indexes only when the required
DocTypes and columns exist.
