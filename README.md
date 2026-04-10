# Shipment Tracking

Shipment Tracking is a plug-and-play Frappe app that integrates Shipkia shipment synchronization and tracking directly inside ERPNext.

It allows ERPNext users to automatically create and monitor shipment records from Sales Invoices while maintaining shipment visibility across relevant documents.

---

## Features

- Create external shipment records automatically from **Sales Invoices**
- Sync shipment data from **Shipkia**
- Store complete **shipment timeline events**
- Display shipment summary on **Sales Invoice**
- Mirror shipment details to **Patient Encounter**
- Add **tracking buttons** directly on Sales Invoice
- Automatically show shipment fields only for **online encounters**

---

## Requirements

- Frappe Framework **v15+**
- ERPNext **v15+**
- Python **3.10+**
- Bench CLI

---

## Installation

Install the app using the Bench CLI.

```bash
cd $PATH_TO_YOUR_BENCH

bench get-app https://github.com/YOUR_GITHUB_USERNAME/shipment_tracking.git

bench --site <your-site-name> install-app shipment_tracking

bench --site <your-site-name> migrate
```

---

## License

MIT
