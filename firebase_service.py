"""Optional Firebase Admin clients for authentication verification and Firestore."""

import json
import os
from pathlib import Path
from threading import Lock

_lock = Lock()
_app = None


def get_firebase_clients():
    """Return (auth, firestore) clients or None when Admin credentials are unavailable."""
    global _app
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not project_id:
        return None

    try:
        import firebase_admin
        from firebase_admin import auth, credentials, firestore
    except ImportError:
        return None

    with _lock:
        if _app is None:
            try:
                _app = firebase_admin.get_app()
            except ValueError:
                credential_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
                credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
                if credential_json:
                    certificate = credentials.Certificate(json.loads(credential_json))
                elif credential_path and Path(credential_path).is_file():
                    certificate = credentials.Certificate(credential_path)
                else:
                    certificate = credentials.ApplicationDefault()
                _app = firebase_admin.initialize_app(
                    certificate,
                    {"projectId": project_id},
                )

    return auth, firestore.client(app=_app)
