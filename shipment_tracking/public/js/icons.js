function injectShipmentIcons() {
    if (document.getElementById("shipment-tracking-icons")) {
        return;
    }

    fetch("/assets/shipment_tracking/icons/shipment_icons.svg")
        .then((res) => res.text())
        .then((svg) => {
            const div = document.createElement("div");
            div.id = "shipment-tracking-icons";
            div.innerHTML = svg;
            document.body.prepend(div);
        })
        .catch((err) => {
            console.warn("Shipment icons could not be loaded.", err);
        });
}

if (typeof frappe !== "undefined" && typeof frappe.ready === "function") {
    frappe.ready(injectShipmentIcons);
} else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectShipmentIcons, { once: true });
} else {
    injectShipmentIcons();
}
