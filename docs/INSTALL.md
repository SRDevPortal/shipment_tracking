# Shipment Tracking - Install

## Bench install

```bash
cd /path/to/frappe-bench
bench get-app /Users/admin/.openclaw/workspace/shipment_tracking
bench --site <your-site> install-app shipment_tracking
bench --site <your-site> migrate
bench --site <your-site> clear-cache
```

If the app is already present in your bench apps directory, use only:

```bash
bench --site <your-site> install-app shipment_tracking
bench --site <your-site> migrate
bench --site <your-site> clear-cache
```

## Required setup after install

Open **Shipment Tracking Settings** and fill:
- Enabled
- Create Order URL
- Tracking URL
- Pickup Address
- Order Channel
- API Key
- API Secret
- Default Parcel Length / Breadth / Height / Dead Weight

## Assumptions

- Sales Invoice is submitted before shipment creation
- Sales Invoice has customer mobile + shipping address
- Existing SRIAAS encounter billing flow writes `source_encounter` when invoice is created from Patient Encounter
- Encounter shipment fields are visible only when `sr_encounter_place = Online`

## Notes

- The app mirrors shipment summary onto both Sales Invoice and Patient Encounter
- Canonical shipment history lives in **Shipment Tracking Shipment**
- Full API debugging lives in **Shipment Tracking Sync Log**
