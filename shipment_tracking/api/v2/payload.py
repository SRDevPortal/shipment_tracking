"""Build and validate New OMS create-order payloads."""

from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata

import frappe
from frappe.utils import cstr

SHIPKIA_ADDRESS_CHARACTERS = set(" #$%&'()*+,-./:;<=>?@[]_{|}")


def sanitize_shipkia_address(value):
    text = cstr(value or "")
    text = (
        text.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", "'")
        .replace("\u201d", "'")
        .replace("\u00a0", " ")
    )
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    text = "".join(
        character
        if character.isalnum() or character in SHIPKIA_ADDRESS_CHARACTERS
        else " "
        for character in text
    )
    return " ".join(text.split())



def money(value):
    """Shipkia V2 documents monetary values as rupees."""
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def weight_in_grams(row):
    value = Decimal(str(row.get("weight_per_unit") or 0))
    if not value:
        return 0
    unit = (row.get("weight_uom") or "Gram").strip().lower()
    factors = {
        "g": Decimal("1"), "gram": Decimal("1"), "grams": Decimal("1"),
        "kg": Decimal("1000"), "kilogram": Decimal("1000"), "kilograms": Decimal("1000"),
        "mg": Decimal("0.001"), "milligram": Decimal("0.001"), "milligrams": Decimal("0.001"),
    }
    if unit not in factors:
        frappe.throw(f"Unsupported item weight unit for V2: {row.get('weight_uom')}")
    return money(value * factors[unit])


def build_payload(invoice, account):
    if account.platform != "New OMS" or not account.v2_contract_verified:
        frappe.throw("Confirm the V2 order API contract and Shipkia-managed products on this account before activation.")
    for field in ("pickup_address", "order_channel", "v2_order_id_path"):
        if not account.get(field):
            frappe.throw("Configure V2 account " + field.replace("_", " "))
    if not account.get_password("api_key", raise_exception=False):
        frappe.throw("Configure the V2 API key.")
    if invoice.currency != "INR":
        frappe.throw("V2 order amounts currently support INR only.")
    shipping_name = invoice.shipping_address_name or invoice.customer_address
    billing_name = invoice.customer_address or shipping_name
    if not shipping_name:
        frappe.throw("Shipping address is required.")
    shipping = frappe.get_doc("Address", shipping_name)
    billing = frappe.get_doc("Address", billing_name)
    phone = getattr(invoice, "contact_mobile", None)
    if invoice.contact_person:
        contact = frappe.get_doc("Contact", invoice.contact_person)
        phone = contact.mobile_no or contact.phone or phone
    phone = phone or shipping.phone
    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10:
        frappe.throw("A valid Indian mobile number is required.")
    phone = "+91-" + digits
    if not all([shipping.address_line1, shipping.pincode]):
        frappe.throw("Shipping address and postal code are required.")
    delivery_address = sanitize_shipkia_address(shipping.address_line1)
    if not delivery_address:
        frappe.throw("Shipping address must contain English letters or numbers.")
    delivery_landmark = sanitize_shipkia_address(shipping.address_line2)

    if invoice.is_return:
        frappe.throw("Return invoices cannot create V2 shipping orders.")
    products = []
    percentage_taxes = [tax for tax in invoice.taxes if (tax.rate or 0) > 0]
    if len(percentage_taxes) > 1 or any(tax.get("charge_type") not in (None, "On Net Total") for tax in percentage_taxes):
        frappe.throw("V2 requires a verified adapter for this invoice tax structure.")
    tax_rate = percentage_taxes[0].rate if percentage_taxes else 0
    prices_include_tax = not percentage_taxes or bool(percentage_taxes[0].get("included_in_print_rate"))
    tax_multiplier = Decimal("1") if prices_include_tax else Decimal("1") + Decimal(str(tax_rate)) / 100
    for row in invoice.items:
        if not row.item_code:
            continue
        if row.qty <= 0 or Decimal(str(row.qty)) != Decimal(str(int(row.qty))) or row.rate < 0:
            frappe.throw("V2 products require positive whole quantities and non-negative prices.")
        products.append({"product_name": row.item_name, "unit_price": money(Decimal(str(row.rate)) * tax_multiplier),
                         "quantity": int(row.qty), "hsn_code": row.get("gst_hsn_code") or account.get("default_hsn_code") or "",
                         "weight": weight_in_grams(row), "tax_rate": tax_rate,
                         "tax_preference": "Inclusive", "product_discount": 0})
    if not products:
        frappe.throw("At least one product is required.")
    if invoice.grand_total < 0 or not 0 <= invoice.outstanding_amount <= invoice.grand_total:
        frappe.throw("Invoice payment amounts require review.")
    payload = {"is_billing_same": shipping_name == billing_name, "product_details": products,
        "pickup_address": account.pickup_address, "order_channel": account.order_channel,
        "delivery_full_name": invoice.customer_name, "delivery_phone": phone,
        "delivery_address": delivery_address,
        "delivery_landmark": delivery_landmark, "delivery_postal_code": shipping.pincode,
        "payment_method": "prepaid" if invoice.outstanding_amount <= 0 else "cod",
        "prepaid_amount": money(max(invoice.grand_total - invoice.outstanding_amount, 0)),
        "shipping_charge": 0, "transaction_charge": 0, "gift_wrap_charge": 0,
        "additional_discount": money(invoice.discount_amount), "order_tag": invoice.name,
        "notes": invoice.remarks or ""}
    for key in ("length", "breadth", "height", "dead_weight"):
        field = "default_parcel_" + key if key in ("length", "breadth", "height") else "default_" + key
        value = account.get(field)
        if value in (None, ""):
            continue
        minimum = 10 if key in ("length", "breadth", "height") else 0
        invalid = value < minimum if minimum else value <= 0
        if invalid:
            requirement = "at least 10 cm" if minimum else "greater than 0 grams"
            frappe.throw("Configure parcel " + key.replace("_", " ") + " " + requirement)
        payload[key] = money(value)
    calculated = sum(
        Decimal(str(product["unit_price"])) * product["quantity"]
        * (Decimal("1") + Decimal(str(product["tax_rate"])) / 100
           if product["tax_preference"] == "Exclusive" else Decimal("1"))
        for product in products
    )
    difference = calculated - Decimal(str(invoice.grand_total))
    payload["additional_discount"] = money(max(difference, Decimal("0")))
    payload["transaction_charge"] = money(max(-difference, Decimal("0")))
    if not payload["is_billing_same"]:
        if not all([billing.address_line1, billing.pincode]):
            frappe.throw("Billing address and postal code are required.")
        billing_address = sanitize_shipkia_address(billing.address_line1)
        if not billing_address:
            frappe.throw("Billing address must contain English letters or numbers.")
        billing_landmark = sanitize_shipkia_address(billing.address_line2)
        payload.update({"billing_full_name": invoice.customer_name, "billing_phone": phone,
            "billing_postal_code": billing.pincode, "billing_address": billing_address,
            "billing_landmark": billing_landmark})
    return payload
