import frappe


def execute():
    frappe.db.sql(
        """
        update `tabShipment WhatsApp Notification`
        set routing_source = null
        where coalesce(channel_account, '') = ''
          and coalesce(conversation, '') = ''
        """
    )
