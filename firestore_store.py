"""Small Firestore document helpers scoped to a verified Firebase UID."""

from firebase_service import get_firebase_clients


class FirestoreUnavailable(RuntimeError):
    pass


def get_store():
    clients = get_firebase_clients()
    if not clients:
        raise FirestoreUnavailable("Firebase Admin is not configured.")
    return clients[1]


def user_ref(store, uid):
    return store.collection("users").document(uid)


def records(store, uid, collection, limit=None):
    query = user_ref(store, uid).collection(collection)
    if limit:
        query = query.limit(limit)
    return [{**snapshot.to_dict(), "id": snapshot.id} for snapshot in query.stream()]


def record_ref(store, uid, collection, record_id):
    return user_ref(store, uid).collection(collection).document(str(record_id))
    
def new_record_ref(store, uid, collection):
    return user_ref(store, uid).collection(collection).document()
