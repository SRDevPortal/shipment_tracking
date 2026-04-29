import frappe

MODULE_NAME = "Shipment Tracking"


def create_cf_with_module(fieldmap: dict[str, list[dict]]):
    for dt, fields in fieldmap.items():
        for field in fields:
            fieldname = field.get("fieldname")

            if field.get("fieldtype") == "Link":
                if not frappe.db.exists("DocType", field.get("options")):
                    frappe.throw(f"DocType '{field.get('options')}' not found.")

            field_data = field.copy()

            meta = frappe.get_meta(dt)
            insert_after = field_data.get("insert_after")
            if insert_after and not meta.has_field(insert_after):
                field_data.pop("insert_after", None)

            existing = frappe.db.get_value(
                "Custom Field",
                {"dt": dt, "fieldname": fieldname},
                "name",
            )

            if not existing and meta.has_field(fieldname):
                frappe.clear_cache(doctype=dt)
                continue

            if existing:
                doc = frappe.get_doc("Custom Field", existing)
                updated = False

                for key, value in field_data.items():
                    if getattr(doc, key, None) != value:
                        setattr(doc, key, value)
                        updated = True

                if updated:
                    doc.save(ignore_permissions=True)
                    frappe.logger("shipment_tracking").info(
                        f"Updated Custom Field: {dt}.{fieldname}"
                    )

                frappe.clear_cache(doctype=dt)
                continue

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

        frappe.clear_cache(doctype=dt)

    frappe.db.commit()
    frappe.clear_cache()


def migrate_custom_field_data(dt: str, source_fieldname: str, target_fieldname: str) -> None:
    if not frappe.db.has_column(dt, source_fieldname):
        return
    if not frappe.db.has_column(dt, target_fieldname):
        return

    table = f"tab{dt}"
    frappe.db.sql(
        f"""
        update `{table}`
        set `{target_fieldname}` = `{source_fieldname}`
        where ifnull(`{target_fieldname}`, '') = ''
          and ifnull(`{source_fieldname}`, '') != ''
        """
    )


def delete_custom_fields(dt: str, fieldnames: list[str]) -> None:
    deleted = False

    for fieldname in fieldnames:
        name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname}, "name")
        if not name:
            continue

        frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
        deleted = True

        frappe.logger("shipment_tracking").info(
            f"Deleted obsolete Custom Field: {dt}.{fieldname}"
        )

    if deleted:
        frappe.db.commit()
        frappe.clear_cache(doctype=dt)


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

    doc = frappe.get_doc(payload).insert(ignore_permissions=True)

    frappe.logger("shipment_tracking").info(
        f"Created Property Setter: {doc_type}.{field_name}.{property_name}"
    )

    frappe.db.commit()
    frappe.clear_cache(doctype=doc_type)

    return doc
