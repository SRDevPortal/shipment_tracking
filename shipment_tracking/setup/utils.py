import frappe

MODULE_NAME = "Shipment Tracking"


def create_cf_with_module(fieldmap: dict[str, list[dict]]):
    for dt, fields in fieldmap.items():

        for field in fields:

            fieldname = field.get("fieldname")

            # Skip if exists
            if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": fieldname}):
                frappe.clear_cache(doctype=dt)   # 🔥 keep meta updated
                continue

            # Validate Link
            if field.get("fieldtype") == "Link":
                if not frappe.db.exists("DocType", field.get("options")):
                    frappe.throw(f"❌ DocType '{field.get('options')}' not found.")

            # 🔥 IMPORTANT: work on copy
            field_data = field.copy()

            # Reload meta
            meta = frappe.get_meta(dt)

            insert_after = field_data.get("insert_after")
            if insert_after and not meta.has_field(insert_after):
                field_data.pop("insert_after", None)

            # Create field
            doc = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": dt,
                "module": MODULE_NAME,
                **field_data,
            })

            doc.insert(ignore_permissions=True)

            frappe.logger("shipment_tracking").info(
                f"Created Custom Field: {dt}.{fieldname}"
            )

        # 🔥 Clear cache once per doctype
        frappe.clear_cache(doctype=dt)

    frappe.db.commit()
    frappe.clear_cache()


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

    # --------------------------------------------------
    # UPDATE EXISTING
    # --------------------------------------------------
    if name:
        doc = frappe.get_doc("Property Setter", name)

        updated = False

        if doc.value != value:
            doc.value = value
            updated = True

        if doc.property_type != property_type:
            doc.property_type = property_type
            updated = True

        if updated:
            doc.save(ignore_permissions=True)

            frappe.logger("shipment_tracking").info(
                f"Updated Property Setter: {doc_type}.{field_name}.{property_name}"
            )

            frappe.db.commit()
            frappe.clear_cache(doctype=doc_type)

        return doc

    # --------------------------------------------------
    # CREATE NEW
    # --------------------------------------------------
    doc = frappe.get_doc(payload).insert(ignore_permissions=True)

    frappe.logger("shipment_tracking").info(
        f"Created Property Setter: {doc_type}.{field_name}.{property_name}"
    )

    frappe.db.commit()
    frappe.clear_cache(doctype=doc_type)

    return doc