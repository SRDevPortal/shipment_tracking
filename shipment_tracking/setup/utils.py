import frappe

MODULE_NAME = "Shipment Tracking"


def create_cf_with_module(fieldmap: dict[str, list[dict]]):
    for dt, fields in fieldmap.items():
        for field in fields:

            # ✅ ADD THIS BLOCK HERE
            if field.get("fieldtype") == "Link":
                if not frappe.db.exists("DocType", field.get("options")):
                    frappe.throw(
                        f"❌ DocType '{field.get('options')}' not found. Install order issue."
                    )

            # existing check
            existing = frappe.db.get_value(
                "Custom Field",
                {"dt": dt, "fieldname": field["fieldname"]},
                "name"
            )
            if existing:
                continue

            doc = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": dt,
                "module": MODULE_NAME,
                **field,
            })
            doc.insert(ignore_permissions=True)


def upsert_property_setter(doc_type: str, field_name: str, property_name: str, value: str, property_type: str):
    name = frappe.db.get_value(
        "Property Setter",
        {
            "doc_type": doc_type,
            "field_name": field_name,
            "property": property_name,
        },
        "name",
    )

    payload = {
        "doctype": "Property Setter",
        "doc_type": doc_type,
        "doctype_or_field": "DocField",
        "field_name": field_name,
        "property": property_name,
        "property_type": property_type,
        "value": value,
        "module": MODULE_NAME,
    }

    if name:
        doc = frappe.get_doc("Property Setter", name)
        doc.value = value
        doc.property_type = property_type
        doc.save(ignore_permissions=True)
        return doc

    return frappe.get_doc(payload).insert(ignore_permissions=True)
