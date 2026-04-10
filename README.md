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
- Maintain real-time shipment visibility inside ERPNext

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
