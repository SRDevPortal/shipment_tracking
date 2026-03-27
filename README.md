### Shipment Tracking

Plug-and-play Frappe app for Shipkia order sync and shipment tracking inside ERPNext.

### What it does

- Creates and tracks external shipment records from Sales Invoices
- Mirrors shipment summary back to Sales Invoice and Patient Encounter
- Stores full shipment timeline events
- Adds tracking buttons on Sales Invoice
- Keeps Patient Encounter shipment fields visible only for online encounters

### Installation

See:
- `docs/INSTALL.md`
- `docs/TESTING_CHECKLIST.md`

Quick bench flow:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app /Users/admin/.openclaw/workspace/shipment_tracking
bench --site <your-site> install-app shipment_tracking
bench --site <your-site> migrate
```
