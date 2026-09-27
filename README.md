# PocketSmart AI

A Flask personal-finance app backed by Firebase Authentication and Cloud Firestore, with transaction management, monthly budgets, savings goals, live analytics, data-derived insights, and a Gemini assistant.

## Features

- Firebase Email/Password registration, verified-email login/logout, profile editing, and Firebase UID-based data ownership.
- Income and expense create, edit, delete, search, filtering, and sorting.
- Monthly category budget limits with usage and over-limit alerts; optional 50/30/20 reference allocation.
- Savings goals with target dates, progress, contributions, editing, and deletion.
- Dashboard and analytics charts rendered from Firestore records.
- Insights computed from the signed-in user's recorded income, expenses, budgets, and goals.
- Gemini API assistant with financial context from the same user's Firestore records. If Gemini is unavailable, the UI reports that instead of generating a fake AI answer.
- Profile documents live at `users/{firebaseUid}`. Finance records live in that user's `expenses`, `income`, `budgets`, and `goals` subcollections.
- No local database is initialized or used. Firestore creates each collection on its first document write; no placeholder financial records are seeded.

## Requirements

- Windows 10 or later
- Python 3.10 or later
- Optional Gemini API key from [Google AI Studio](https://aistudio.google.com/)

## Windows Setup

Open PowerShell in the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that PowerShell window, then activate the environment again.

The current Google GenAI package is included in `requirements.txt`. To install it separately if needed:

```powershell
py -m pip install google-genai
```

Create a local `.env` file in the project root:

Edit `.env` and set:

```env
GEMINI_API_KEY=your_key_from_google_ai_studio
GEMINI_MODEL=gemini-2.5-flash
SECRET_KEY=replace_with_a_long_random_secret
FLASK_DEBUG=false
FIREBASE_API_KEY=your_firebase_web_api_key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_STORAGE_BUCKET=your-project.firebasestorage.app
FIREBASE_MESSAGING_SENDER_ID=your-sender-id
FIREBASE_APP_ID=your-web-app-id
GOOGLE_APPLICATION_CREDENTIALS=D:/secure/firebase-service-account.json
```

The Gemini key and Admin credential path are read only by Flask. Firebase web config is public client configuration. Keep `.env` and the Admin service-account JSON private; both are ignored by Git.

### Firebase Auth and Firestore

Enable **Email/Password** in Firebase Authentication. The browser signs users in with Firebase, and Flask verifies the ID token before creating a session. Profiles and all financial data are stored under `users/{firebaseUid}` in Firestore. Admin SDK operations bypass Firestore Security Rules; keep credentials private and enforce user scoping in server routes.

Install the server SDK from `requirements.txt` and provide Firebase Admin credentials. For local development, create a service account with only the required Firebase Authentication and Firestore permissions, store its JSON file outside this repository, and set the path in `.env`:

```env
GOOGLE_APPLICATION_CREDENTIALS=D:/secure/firebase-service-account.json
```

On a cloud host, attach a dedicated service account and use Application Default Credentials. Never commit its JSON file or expose its private key in frontend code. Restart Flask after setting credentials. If Admin credentials are missing, Firebase-backed routes report that the service is unavailable.

Run the application:

```powershell
py app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Create an account to start; new accounts begin with no assumed income, expenses, or savings goals.

## Tests

Run the integration suite:

```powershell
py -m unittest discover -s tests -v
```

Tests use an in-memory Firestore fake; they do not write to your Firebase project.

## Common Issues

- **`AI assistant is temporarily unavailable`:** Check that `.env` has a valid `GEMINI_API_KEY`, that the selected model is available to your Google AI Studio account, and that the machine can reach Google’s API. Restart Flask after changing `.env`.
- **PowerShell does not allow activation:** Use the process-scoped execution policy command above. It affects only the current PowerShell process.
- **Port 5000 is occupied:** Stop the other local Flask process, or change the `port=5000` value at the bottom of `app.py` and open the corresponding localhost URL.
- **Firebase unavailable:** Check that `firebase-admin` is installed, the service-account path is valid (or the host has Application Default Credentials), and the service account has Firebase Auth and Firestore permissions.

## Project Structure

```text
database/               Local SQLite database (ignored by Git)
app.py                  Flask routes, Firestore operations, and Gemini integration
firebase_service.py     Firebase Admin initialization
firestore_store.py      UID-scoped Firestore document helpers
templates/              Jinja pages and shared navigation/flash partials
static/css/style.css    Responsive application styles
static/js/main.js       Shared authentication form behavior
tests/test_app.py       In-memory Firestore workflow tests
requirements.txt        Runtime dependencies
.env.example            Environment variable template
```
