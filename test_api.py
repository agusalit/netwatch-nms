from app.models.device import Device


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_loads(client):
    response = client.get("/")
    assert response.status_code == 200


def test_create_device_appears_in_grid(client):
    response = client.post("/devices", data={
        "name": "Test Device",
        "ip_address": "10.0.0.5",
        "group": "Room",
        "monitor_type": "icmp",
    })
    assert response.status_code == 200
    assert "Test Device" in response.text


def test_duplicate_ip_shows_inline_error_not_500(client):
    payload = {
        "name": "Dup A",
        "ip_address": "10.0.0.9",
        "group": "Room",
        "monitor_type": "icmp",
    }
    first = client.post("/devices", data=payload)
    assert first.status_code == 200

    second = client.post("/devices", data={**payload, "name": "Dup B"})
    # The known gap we fixed: this used to be an unhandled 500.
    assert second.status_code == 200
    assert "already exists" in second.text
    assert "Dup B" not in second.text  # the duplicate was never actually created


def test_delete_device(client, db_session):
    client.post("/devices", data={
        "name": "ToDelete",
        "ip_address": "10.0.0.20",
        "group": "Room",
        "monitor_type": "icmp",
    })
    device = db_session.query(Device).filter(Device.ip_address == "10.0.0.20").first()
    assert device is not None

    response = client.delete(f"/devices/{device.id}")
    assert response.status_code == 200
    assert "ToDelete" not in response.text


def test_edit_device_form_prefills_existing_values(client, db_session):
    client.post("/devices", data={
        "name": "EditMe",
        "ip_address": "10.0.0.30",
        "group": "Office",
        "monitor_type": "icmp",
    })
    device = db_session.query(Device).filter(Device.ip_address == "10.0.0.30").first()

    response = client.get(f"/devices/{device.id}/edit")
    assert response.status_code == 200
    assert "EditMe" in response.text
    assert "10.0.0.30" in response.text


def test_edit_nonexistent_device_returns_404(client):
    response = client.get("/devices/999999/edit")
    assert response.status_code == 404