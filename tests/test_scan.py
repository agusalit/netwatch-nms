def test_scan_invalid_cidr_shows_error(client):
    response = client.post("/scan", data={"cidr": "not-a-network"})
    assert response.status_code == 200
    assert "not a valid network range" in response.text


def test_scan_range_too_large_shows_error(client):
    # A /16 has 65,534 usable hosts — well over the 256-address cap.
    response = client.post("/scan", data={"cidr": "10.0.0.0/16"})
    assert response.status_code == 200
    assert "too large" in response.text.lower()


def test_scan_form_loads(client):
    response = client.get("/scan/new")
    assert response.status_code == 200