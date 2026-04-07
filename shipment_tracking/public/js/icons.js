frappe.ready(() => {
    fetch("/assets/shipment_tracking/icons/shipment_icons.svg")
        .then(res => res.text())
        .then(svg => {
            const div = document.createElement("div");
            div.innerHTML = svg;
            document.body.prepend(div);
        });
});