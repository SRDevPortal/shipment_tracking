# Shipment Tracking - Testing Checklist

## 1. Installation sanity

- [ ] `bench --site <site> install-app shipment_tracking` succeeds
- [ ] `bench --site <site> migrate` succeeds
- [ ] DocTypes are visible:
  - [ ] Shipment Tracking Settings
  - [ ] Shipment Tracking Shipment
  - [ ] Shipment Tracking Sync Log

## 2. Custom field sanity

### Sales Invoice
- [ ] `source_encounter` field exists
- [ ] `shipkia_order_id` exists
- [ ] `shipkia_awb_number` exists
- [ ] `shipkia_status` exists
- [ ] `shipkia_estimated_delivery` exists
- [ ] `shipkia_delivered_on` exists
- [ ] `shipkia_shipment` exists

### Patient Encounter
- [ ] `shipkia_order_id` exists
- [ ] `shipkia_awb_number` exists
- [ ] `shipkia_status` exists
- [ ] `shipkia_estimated_delivery` exists
- [ ] `shipkia_delivered_on` exists
- [ ] `shipkia_shipment` exists
- [ ] shipment section shows only when encounter place is `Online`

## 3. Outbound order creation

Use a submitted Sales Invoice with:
- [ ] patient linked
- [ ] valid contact mobile
- [ ] valid shipping address
- [ ] at least one item row

Then test:
- [ ] **Send to Shipkia** button appears on submitted Sales Invoice
- [ ] button creates external order successfully
- [ ] Shipkia response returns usable `docs[0].name`
- [ ] `Shipment Tracking Shipment` record is created
- [ ] Sales Invoice gets:
  - [ ] shipkia_order_id
  - [ ] shipkia_shipment
- [ ] linked Patient Encounter gets:
  - [ ] shipkia_order_id
  - [ ] shipkia_shipment
- [ ] Sync Log row is created for Create Order

## 4. Encounter linkage validation

### Preferred path
- [ ] invoice created from Patient Encounter carries `source_encounter`
- [ ] shipment mirrors back to the exact same encounter

### Fallback path
- [ ] if `source_encounter` missing, remarks parser or patient fallback still links reasonably

## 5. Tracking sync

Using a known Shipkia order id:
- [ ] **Refresh Shipment Status** works from Sales Invoice
- [ ] shipment summary updates on Shipment Tracking Shipment
- [ ] AWB updates
- [ ] status updates
- [ ] normalized status updates
- [ ] ETA updates
- [ ] delivered_on updates when available
- [ ] timeline rows append without duplicates
- [ ] Sync Log row is created for Track Shipment

## 6. UI sanity

- [ ] **Open Shipment** button opens the canonical shipment record
- [ ] **Resend to Shipkia** appears after initial send
- [ ] resend requires explicit confirmation

## 7. Error-path sanity

- [ ] missing shipping address throws useful error
- [ ] bad mobile number throws useful error
- [ ] disabled settings block API calls
- [ ] invalid API auth creates failed Sync Log row
- [ ] non-JSON error responses still get logged cleanly
- [ ] tracking response without result is handled visibly

## 8. Scheduler sanity

- [ ] hourly scheduler can call `shipment_tracking.api.tracking.sync_active_shipments`
- [ ] delivered shipments are skipped from active sync
- [ ] failures log to Error Log without killing the whole loop

## 9. Suggested manual test cases

- [ ] prepaid shipment
- [ ] COD shipment
- [ ] separate billing and delivery address
- [ ] online encounter
- [ ] OPD encounter should not show shipment fields
- [ ] delivered shipment
- [ ] RTO / exception-like shipment if available
