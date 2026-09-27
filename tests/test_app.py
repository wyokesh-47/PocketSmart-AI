import os
import unittest
from unittest.mock import Mock, patch

import app as pocketsmart
import firestore_store


class Snapshot:
    def __init__(self, document_id, data):
        self.id = document_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class DocumentReference:
    def __init__(self, store, path):
        self.store = store
        self.path = path
        self.id = path[-1]

    def get(self):
        return Snapshot(self.id, self.store.documents.get(self.path))

    def set(self, data, merge=False):
        current = self.store.documents.get(self.path, {}) if merge else {}
        self.store.documents[self.path] = {**current, **data}

    def update(self, data):
        if self.path not in self.store.documents:
            raise KeyError(self.id)
        self.store.documents[self.path].update(data)

    def delete(self):
        self.store.documents.pop(self.path, None)

    def collection(self, name):
        return CollectionReference(self.store, self.path + (name,))


class CollectionReference:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def document(self, document_id=None):
        if document_id is None:
            self.store.next_id += 1
            document_id = f"doc-{self.store.next_id}"
        return DocumentReference(self.store, self.path + (str(document_id),))

    def stream(self):
        depth = len(self.path) + 1
        return [
            Snapshot(path[-1], data)
            for path, data in self.store.documents.items()
            if len(path) == depth and path[:-1] == self.path
        ]

    def limit(self, _count):
        return self


class FakeFirestore:
    def __init__(self):
        self.documents = {}
        self.next_id = 0

    def collection(self, name):
        return CollectionReference(self, (name,))


class PocketSmartFirestoreTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeFirestore()
        self.email = f"user-{id(self)}@example.test"
        self.uid = f"firebase-{id(self)}"
        self.auth = Mock()
        self.auth.verify_id_token.side_effect = lambda token, check_revoked: {
            "uid": self.uid,
            "email": self.email,
            "name": "Firestore Test User",
            "email_verified": True,
        }
        self.clients_patch = patch.object(
            pocketsmart, "get_firebase_clients", return_value=(self.auth, self.store)
        )
        self.clients_patch.start()
        self.addCleanup(self.clients_patch.stop)
        self.store_clients_patch = patch.object(
            firestore_store, "get_firebase_clients", return_value=(self.auth, self.store)
        )
        self.store_clients_patch.start()
        self.addCleanup(self.store_clients_patch.stop)
        pocketsmart.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = pocketsmart.app.test_client()
        response = self.client.post("/auth/firebase", json={"idToken": "signed-test-token"})
        self.assertEqual(response.status_code, 200)

    def records(self, collection, uid=None):
        return pocketsmart.records(self.store, uid or self.uid, collection)

    def test_auth_profile_and_pages_use_firestore(self):
        profile_path = ("users", self.uid)
        self.assertEqual(self.store.documents[profile_path]["email"], self.email)
        for path in (
            "/dashboard", "/expenses", "/income", "/budget", "/goals",
            "/profile", "/analytics", "/recommendations", "/ai",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertFalse(hasattr(pocketsmart, "get_db"))
        self.assertFalse(os.path.exists("database/pocketsmart.db"))

    def test_finance_crud_search_budget_and_goals(self):
        self.client.post("/expenses", data={
            "amount": "125.50", "category": "Food", "description": "Audit lunch",
            "date": "2026-09-12",
        })
        self.client.post("/income", data={
            "amount": "2000", "source": "Salary", "date": "2026-09-01",
        })
        self.client.post("/budget", data={"category": "Food", "amount": "500"})
        self.client.post("/goals", data={
            "name": "Laptop", "target": "1000", "saved": "50", "deadline": "2026-12-31",
        })
        expense = self.records("expenses")[0]
        income = self.records("income")[0]
        goal = self.records("goals")[0]
        self.assertEqual(len(self.records("budgets")), 1)
        self.assertEqual(self.client.get("/expenses?q=lunch&category=Food").status_code, 200)
        self.assertIn(b"<progress", self.client.get("/budget").data)
        self.assertEqual(self.client.post(f"/expenses/{expense['id']}/edit", data={
            "amount": "130", "category": "Food", "description": "Updated", "date": "2026-09-12",
        }).status_code, 302)
        self.assertEqual(self.client.post(f"/income/{income['id']}/edit", data={
            "amount": "2100", "source": "Salary", "date": "2026-09-01",
        }).status_code, 302)
        self.assertEqual(self.client.post(f"/goals/{goal['id']}/edit", data={
            "name": "Edited laptop", "target": "1200", "saved": "70", "deadline": "2026-12-31",
        }).status_code, 302)
        self.assertEqual(self.client.post(f"/goals/contribute/{goal['id']}", data={"amount": "25"}).status_code, 302)
        self.assertEqual(self.client.post(f"/api/delete-expense/{expense['id']}").status_code, 302)
        self.assertEqual(self.client.post(f"/api/delete-income/{income['id']}").status_code, 302)
        self.assertEqual(self.client.post(f"/api/delete-goal/{goal['id']}").status_code, 302)

    def test_financial_records_are_scoped_to_firebase_uid(self):
        self.client.post("/expenses", data={
            "amount": "120", "category": "Food", "description": "Private", "date": "2026-09-12",
        })
        expense = self.records("expenses")[0]
        other_uid = "another-firebase-user"
        other_client = pocketsmart.app.test_client()
        self.auth.verify_id_token.side_effect = lambda token, check_revoked: {
            "uid": other_uid, "email": "other@example.test", "email_verified": True,
        }
        self.assertEqual(other_client.post("/auth/firebase", json={"idToken": "other-token"}).status_code, 200)
        other_client.post(f"/expenses/{expense['id']}/edit", data={
            "amount": "1", "category": "Changed", "description": "", "date": "2026-09-12",
        })
        unchanged = pocketsmart.record_ref(self.store, self.uid, "expenses", expense["id"]).get().to_dict()
        self.assertEqual(unchanged["category"], "Food")

    def test_profile_updates_firestore_and_firebase_auth(self):
        response = self.client.post("/profile", data={"name": "Updated Name", "email": self.email})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.store.documents[("users", self.uid)]["name"], "Updated Name")
        self.auth.update_user.assert_called_once_with(self.uid, display_name="Updated Name")

    def test_unverified_email_and_missing_firebase_are_rejected(self):
        self.auth.verify_id_token.side_effect = lambda token, check_revoked: {
            "uid": "unverified", "email": "unverified@example.test", "email_verified": False,
        }
        response = self.client.post("/auth/firebase", json={"idToken": "unverified-token"})
        self.assertEqual(response.status_code, 403)
        with patch.object(pocketsmart, "get_firebase_clients", return_value=None):
            unavailable = pocketsmart.app.test_client().post("/auth/firebase", json={"idToken": "token"})
        self.assertEqual(unavailable.status_code, 503)

    def test_gemini_context_comes_from_firestore(self):
        self.client.post("/income", data={"amount": "3000", "source": "Salary", "date": "2026-09-10"})
        self.client.post("/expenses", data={
            "amount": "450", "category": "Food", "description": "Lunch", "date": "2026-09-12",
        })
        fake_client = Mock()
        fake_client.models.generate_content.return_value = Mock(text="Your recorded difference is ₹2,550.")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key", "GEMINI_MODEL": "gemini-test-model"}), \
             patch("google.genai.Client", return_value=fake_client):
            response = self.client.post("/api/ai", json={"message": "How much can I save?"})
        self.assertEqual(response.status_code, 200)
        prompt = fake_client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("₹3,000.00", prompt)
        self.assertIn("₹450.00", prompt)

    def test_invalid_amount_is_rejected_without_firestore_write(self):
        response = self.client.post("/expenses", data={
            "amount": "nan", "category": "Food", "description": "Invalid", "date": "2026-09-12",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.records("expenses"), [])

    def test_firestore_chart_data_uses_stored_documents(self):
        self.client.post("/income", data={"amount": "2000", "source": "Salary", "date": "2026-09-01"})
        self.client.post("/expenses", data={
            "amount": "500", "category": "Food", "description": "Groceries", "date": "2026-09-02",
        })
        response = self.client.get("/api/chart-data")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["totalIncome"], 2000)
        self.assertEqual(data["totalExpenses"], 500)


if __name__ == "__main__":
    unittest.main()
