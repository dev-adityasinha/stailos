"""Phase 3 verification: customers, lead conversion, properties, bookings."""
from tests.conftest import auth_headers, create_user_as_admin
from tests.test_leads import make_lead


def make_project(client, headers, **overrides):
    payload = {
        "name": "Prestige Lakeside",
        "builder_name": "Prestige Group",
        "location": "Varthur Road, Whitefield",
        "city": "Bangalore",
        "amenities": ["Pool", "Gym", "Clubhouse"],
        "rera_id": "PRM/KA/RERA/1251/446",
        "units": [
            {"unit_number": "A-101", "floor": 1, "unit_type": "2BHK",
             "carpet_area_sqft": 1050, "price": 7500000, "facing": "East"},
            {"unit_number": "A-102", "floor": 1, "unit_type": "3BHK",
             "carpet_area_sqft": 1450, "price": 11000000, "facing": "North"},
            {"unit_number": "B-201", "floor": 2, "unit_type": "3BHK",
             "carpet_area_sqft": 1500, "price": 12000000, "facing": "East"},
        ],
    }
    payload.update(overrides)
    return client.post("/api/v1/properties/projects", headers=headers, json=payload)


def make_customer(client, headers, **overrides):
    payload = {
        "full_name": "Sunita Verma",
        "phone": "9811122233",
        "email": "sunita@example.com",
        "city": "Bangalore",
        "budget_min": 7000000,
        "budget_max": 12000000,
        "family_info": [{"name": "Raj Verma", "relation": "spouse", "age": 41}],
        "preferences": {"property_type": "3BHK", "facing": "East"},
    }
    payload.update(overrides)
    return client.post("/api/v1/customers", headers=headers, json=payload)


class TestCustomers:
    def test_crud_and_360(self, client, admin):
        resp = make_customer(client, admin)
        assert resp.status_code == 201, resp.text
        customer = resp.json()["data"]
        assert customer["family_info"][0]["relation"] == "spouse"

        resp = client.patch(
            f"/api/v1/customers/{customer['id']}", headers=admin,
            json={"occupation": "Software Architect", "company": "Infosys"},
        )
        assert resp.json()["data"]["occupation"] == "Software Architect"

        full = client.get(
            f"/api/v1/customers/{customer['id']}/360", headers=admin
        ).json()["data"]
        assert full["customer"]["id"] == customer["id"]
        assert full["bookings"] == [] and full["properties"] == []
        assert any(a["type"] == "created" for a in full["timeline"])

        assert client.delete(
            f"/api/v1/customers/{customer['id']}", headers=admin
        ).status_code == 200
        assert client.get(
            f"/api/v1/customers/{customer['id']}", headers=admin
        ).status_code == 404

    def test_lead_conversion(self, client, admin):
        lead = make_lead(client, admin).json()["data"]
        resp = client.post(
            f"/api/v1/leads/{lead['id']}/convert", headers=admin,
            json={"city": "Bangalore", "occupation": "Doctor"},
        )
        assert resp.status_code == 201, resp.text
        customer = resp.json()["data"]
        assert customer["full_name"] == lead["full_name"]
        assert customer["lead_id"] == lead["id"]
        assert customer["preferences"]["property_type"] == lead["property_type"]
        # Lead now linked; second conversion blocked.
        updated_lead = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert updated_lead["customer_id"] == customer["id"]
        resp = client.post(f"/api/v1/leads/{lead['id']}/convert", headers=admin, json={})
        assert resp.status_code == 409

    def test_scope_isolation(self, client, admin):
        create_user_as_admin(client, admin, "repa@stail.com", "sales_executive")
        create_user_as_admin(client, admin, "repb@stail.com", "sales_executive")
        rep_a, rep_b = auth_headers(client, "repa@stail.com"), auth_headers(client, "repb@stail.com")
        make_customer(client, rep_a)
        assert client.get("/api/v1/customers", headers=rep_b).json()["meta"]["total"] == 0
        assert client.get("/api/v1/customers", headers=admin).json()["meta"]["total"] == 1


class TestProperties:
    def test_admin_creates_inventory_others_cannot(self, client, admin):
        assert make_project(client, admin).status_code == 201
        create_user_as_admin(client, admin, "rep@stail.com", "sales_executive")
        rep = auth_headers(client, "rep@stail.com")
        assert make_project(client, rep).status_code == 403

    def test_search_filters(self, client, admin):
        make_project(client, admin)
        all_units = client.get("/api/v1/properties", headers=admin).json()
        assert all_units["meta"]["total"] == 3
        bhk3 = client.get("/api/v1/properties?unit_type=3BHK", headers=admin).json()
        assert bhk3["meta"]["total"] == 2
        priced = client.get(
            "/api/v1/properties?max_price=8000000", headers=admin
        ).json()
        assert priced["meta"]["total"] == 1
        by_text = client.get("/api/v1/properties?q=prestige", headers=admin).json()
        assert by_text["meta"]["total"] == 3

    def test_shortlist_favourite_attach_and_compare(self, client, admin):
        make_project(client, admin)
        units = client.get("/api/v1/properties", headers=admin).json()["data"]
        customer = make_customer(client, admin).json()["data"]

        resp = client.post(
            f"/api/v1/properties/{units[0]['id']}/shortlist", headers=admin,
            json={"customer_id": customer["id"]},
        )
        assert resp.status_code == 201
        # Duplicate shortlist blocked.
        resp = client.post(
            f"/api/v1/properties/{units[0]['id']}/shortlist", headers=admin,
            json={"customer_id": customer["id"]},
        )
        assert resp.status_code == 409
        client.post(
            f"/api/v1/properties/{units[1]['id']}/favourite", headers=admin,
            json={"customer_id": customer["id"]},
        )
        links = client.get(
            f"/api/v1/properties/customer/{customer['id']}", headers=admin
        ).json()["data"]
        assert {l["relation"] for l in links} == {"shortlisted", "favourite"}

        comp = client.post(
            "/api/v1/properties/compare", headers=admin,
            json={"unit_ids": [units[0]["id"], units[1]["id"]]},
        ).json()["data"]
        assert len(comp) == 2 and comp[0]["project"]["name"] == "Prestige Lakeside"


class TestBookings:
    def _setup(self, client, admin):
        make_project(client, admin)
        units = client.get("/api/v1/properties", headers=admin).json()["data"]
        customer = make_customer(client, admin).json()["data"]
        return units, customer

    def _create_booking(self, client, admin, unit, customer, **overrides):
        payload = {
            "customer_id": customer["id"], "unit_id": unit["id"],
            "total_value": 11000000, "token_amount": 500000,
        }
        payload.update(overrides)
        return client.post("/api/v1/bookings", headers=admin, json=payload)

    def test_full_lifecycle_to_possession(self, client, admin):
        units, customer = self._setup(client, admin)
        booking = self._create_booking(client, admin, units[1], customer).json()["data"]
        assert booking["stage"] == "site_visit"

        # site_visit → booking (unit becomes booked)
        b = client.post(
            f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={}
        ).json()["data"]
        assert b["stage"] == "booking"
        unit = client.get(f"/api/v1/properties/{units[1]['id']}", headers=admin).json()["data"]
        assert unit["status"] == "booked"

        # → documentation → payment
        client.post(f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={})
        b = client.post(
            f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={}
        ).json()["data"]
        assert b["stage"] == "payment"

        # possession blocked until fully paid
        resp = client.post(
            f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={}
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "payment_incomplete"

        # pay in two installments; overpayment rejected
        client.post(
            f"/api/v1/bookings/{booking['id']}/payments", headers=admin,
            json={"amount": 5000000, "milestone": "Down payment"},
        )
        resp = client.post(
            f"/api/v1/bookings/{booking['id']}/payments", headers=admin,
            json={"amount": 7000000},
        )
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "overpayment"
        resp = client.post(
            f"/api/v1/bookings/{booking['id']}/payments", headers=admin,
            json={"amount": 6000000, "milestone": "Final"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["receipt_number"].startswith("RCPT-")

        # → possession → completed (unit sold)
        b = client.post(
            f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={}
        ).json()["data"]
        assert b["stage"] == "possession"
        b = client.post(
            f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={}
        ).json()["data"]
        assert b["stage"] == "completed" and b["status"] == "completed"
        unit = client.get(f"/api/v1/properties/{units[1]['id']}", headers=admin).json()["data"]
        assert unit["status"] == "sold"
        # Stage history recorded every hop.
        detail = client.get(f"/api/v1/bookings/{booking['id']}", headers=admin).json()["data"]
        assert len(detail["stage_events"]) == 6
        assert len(detail["payments"]) == 2

    def test_unit_double_booking_blocked(self, client, admin):
        units, customer = self._setup(client, admin)
        self._create_booking(client, admin, units[0], customer)
        customer2 = make_customer(
            client, admin, full_name="Anil Kapoor", phone="9822233344",
            email="anil@example.com",
        ).json()["data"]
        resp = self._create_booking(client, admin, units[0], customer2)
        assert resp.status_code == 409

    def test_cancel_frees_unit(self, client, admin):
        units, customer = self._setup(client, admin)
        booking = self._create_booking(client, admin, units[0], customer).json()["data"]
        client.post(f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={})
        resp = client.post(
            f"/api/v1/bookings/{booking['id']}/cancel", headers=admin,
            json={"reason": "Customer chose another project"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"
        unit = client.get(f"/api/v1/properties/{units[0]['id']}", headers=admin).json()["data"]
        assert unit["status"] == "available"
        # No further stage moves or payments on a cancelled booking.
        assert client.post(
            f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={}
        ).status_code == 400
        assert client.post(
            f"/api/v1/bookings/{booking['id']}/payments", headers=admin,
            json={"amount": 1000},
        ).status_code == 400

    def test_booking_from_lead_updates_lead_stage(self, client, admin):
        units, customer = self._setup(client, admin)
        lead = make_lead(client, admin, phone="9877700011", email="l2@x.com",
                         full_name="Booker Lead").json()["data"]
        booking = self._create_booking(
            client, admin, units[2], customer, lead_id=lead["id"]
        ).json()["data"]
        lead_now = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert lead_now["stage"] == "site_visit_scheduled"
        client.post(f"/api/v1/bookings/{booking['id']}/advance-stage", headers=admin, json={})
        lead_now = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]
        assert lead_now["stage"] == "booked"

    def test_customer_360_shows_booking(self, client, admin):
        units, customer = self._setup(client, admin)
        self._create_booking(client, admin, units[0], customer)
        full = client.get(
            f"/api/v1/customers/{customer['id']}/360", headers=admin
        ).json()["data"]
        assert len(full["bookings"]) == 1
        assert any("Booking started" in a["title"] for a in full["timeline"])
