from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import os
import math
from datetime import datetime
from functools import wraps
from urllib.parse import quote
from dotenv import load_dotenv
from firebase_service import get_firebase_clients
from firestore_store import get_store, new_record_ref, record_ref, records, user_ref

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(32)

@app.context_processor
def inject_firebase_web_config():
    return {"firebase_web_config": {
        "apiKey": os.getenv("FIREBASE_API_KEY", ""),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
        "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId": os.getenv("FIREBASE_APP_ID", ""),
    }}

def firebase_server_ready():
    try:
        return get_firebase_clients() is not None
    except Exception:
        return False

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access this page.", "info")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    try:
        snapshot = user_ref(get_store(), uid).get()
        return {**snapshot.to_dict(), "id": uid} if snapshot.exists else None
    except Exception:
        app.logger.warning("Could not load Firebase profile for authenticated user")
        return None

def parse_amount(value):
    amount = float(value)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Amount must be a positive number.")
    return amount

def parse_date(value):
    date_value = value or datetime.now().strftime("%Y-%m-%d")
    datetime.strptime(date_value, "%Y-%m-%d")
    return date_value

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return render_template("signup.html", name=name, email=email, firebase_server_ready=firebase_server_ready())
        if password != confirm:
            flash("Passwords do not match. Please re-enter.", "error")
            return render_template("signup.html", name=name, email=email, firebase_server_ready=firebase_server_ready())
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("signup.html", name=name, email=email, firebase_server_ready=firebase_server_ready())
        if "@" not in email or len(name) > 80:
            flash("Enter a valid email and a name under 80 characters.", "error")
            return render_template("signup.html", name=name, email=email, firebase_server_ready=firebase_server_ready())
        flash("Complete account creation through Firebase Auth, then verify your email.", "error")
        return render_template("signup.html", name=name, email=email, firebase_server_ready=firebase_server_ready())

    return render_template("signup.html", firebase_server_ready=firebase_server_ready())

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        flash("Sign in through Firebase Auth to continue.", "error")
    return render_template("login.html", firebase_server_ready=firebase_server_ready())

@app.route("/auth/firebase", methods=["POST"])
def firebase_login():
    data = request.get_json(silent=True) or {}
    id_token = data.get("idToken", "")
    display_name = (data.get("name") or "").strip()[:80]
    if not id_token:
        return jsonify({"error": "Firebase sign-in token is required."}), 400
    try:
        clients = get_firebase_clients()
        if not clients:
            return jsonify({"error": "Firebase Admin is not configured on the server. Set up firebase-admin and server credentials."}), 503
        firebase_auth, firestore = clients
        decoded = firebase_auth.verify_id_token(id_token, check_revoked=True)
        if not decoded.get("email_verified"):
            return jsonify({"error": "Verify your email address before continuing."}), 403
        firebase_uid = decoded["uid"]
        email = (decoded.get("email") or "").strip().lower()
        if not email:
            return jsonify({"error": "A verified email is required for this account."}), 400
        name = display_name or decoded.get("name") or email.split("@", 1)[0]
        profile_ref = user_ref(firestore, firebase_uid)
        old_profile = profile_ref.get().to_dict() or {}
        profile_ref.set({
            "uid": firebase_uid,
            "name": name,
            "email": email,
            "created_at": old_profile.get("created_at", datetime.utcnow().isoformat()),
            "provider": "firebase-auth",
            "updated_at": datetime.utcnow().isoformat(),
        }, merge=True)
        session.clear()
        session["user_id"] = firebase_uid
        session["user_name"] = name
        return jsonify({"redirect": url_for("dashboard")})
    except Exception:
        app.logger.warning("Firebase authentication exchange failed")
        return jsonify({"error": "Could not verify Firebase sign-in. Check the server credentials and Firebase project configuration."}), 401

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been successfully logged out.", "info")
    return render_template("firebase-logout.html", firebase_web_config=inject_firebase_web_config()["firebase_web_config"])

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    store = get_store()
    income_rows = records(store, uid, "income")
    expense_rows = records(store, uid, "expenses")
    goal_rows = records(store, uid, "goals")
    income = sum(row.get("amount", 0) for row in income_rows)
    expenses = sum(row.get("amount", 0) for row in expense_rows)
    balance = income - expenses
    category_map = {}
    for row in expense_rows:
        category = row.get("category", "Other")
        category_map.setdefault(category, {"category": category, "total": 0, "count": 0})
        category_map[category]["total"] += row.get("amount", 0)
        category_map[category]["count"] += 1
    categories = sorted(category_map.values(), key=lambda row: row["total"], reverse=True)
    recent_expenses = sorted(expense_rows, key=lambda row: (row.get("date", ""), row.get("created_at", "")), reverse=True)[:6]
    recent_income = sorted(income_rows, key=lambda row: (row.get("date", ""), row.get("created_at", "")), reverse=True)[:4]
    goals = sorted(goal_rows, key=lambda row: row.get("created_at", ""), reverse=True)[:4]

    savings_rate = round(((income - expenses) / income * 100), 1) if income > 0 else 0

    return render_template(
        "dashboard.html",
        user=current_user(),
        income=income,
        expenses=expenses,
        balance=balance,
        savings_rate=savings_rate,
        categories=categories,
        recent_expenses=recent_expenses,
        recent_income=recent_income,
        goals=goals
    )

@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    uid = session["user_id"]
    store = get_store()
    if request.method == "POST":
        try:
            amount = parse_amount(request.form.get("amount", ""))
            category = request.form.get("category", "Other").strip()[:60]
            description = request.form.get("description", "").strip()[:200]
            date = parse_date(request.form.get("date", ""))
            if not category:
                raise ValueError("Choose a category.")
            firestore_record = new_record_ref(store, uid, "expenses")
            firestore_record.set({"amount": amount, "category": category, "description": description, "date": date, "created_at": datetime.utcnow().isoformat()})
            flash(f"Added expense: ₹{amount:,.2f} for {category}", "success")
        except (ValueError, TypeError):
            flash("Enter a valid positive amount, category, and date.", "error")
        except Exception:
            app.logger.warning("Could not save expense to Firestore")
            flash("Could not save this expense to Firestore. Please try again.", "error")
        return redirect(url_for("expenses"))

    search = request.args.get("q", "").strip()[:100]
    category = request.args.get("category", "").strip()[:60]
    start_date = request.args.get("from", "").strip()
    end_date = request.args.get("to", "").strip()
    sort = request.args.get("sort", "newest")
    order_by = {"oldest": "date ASC, id ASC", "amount-high": "amount DESC, date DESC", "amount-low": "amount ASC, date DESC"}.get(sort, "date DESC, id DESC")
    rows = records(store, uid, "expenses")
    total_spent = sum(row.get("amount", 0) for row in rows)
    categories = [{"category": value} for value in sorted({row.get("category", "Other") for row in rows})]
    rows = [row for row in rows if not search or search.casefold() in (row.get("description", "") + " " + row.get("category", "")).casefold()]
    rows = [row for row in rows if not category or row.get("category") == category]
    rows = [row for row in rows if not start_date or row.get("date", "") >= start_date]
    rows = [row for row in rows if not end_date or row.get("date", "") <= end_date]
    rows.sort(key=lambda row: (row.get("date", ""), row.get("created_at", "")), reverse=sort not in ("oldest", "amount-high", "amount-low"))
    if sort == "amount-high":
        rows.sort(key=lambda row: row.get("amount", 0), reverse=True)
    elif sort == "amount-low":
        rows.sort(key=lambda row: row.get("amount", 0))
    return render_template("expenses.html", expenses=rows, total_spent=total_spent, categories=categories, user=current_user(), filters={"q": search, "category": category, "from": start_date, "to": end_date, "sort": sort})

@app.route("/expenses/<expense_id>/edit", methods=["POST"])
@login_required
def edit_expense(expense_id):
    try:
        amount = parse_amount(request.form.get("amount", ""))
        category = request.form.get("category", "Other").strip()[:60]
        description = request.form.get("description", "").strip()[:200]
        date = parse_date(request.form.get("date", ""))
        ref = record_ref(get_store(), session["user_id"], "expenses", expense_id)
        if not ref.get().exists:
            flash("Expense not found.", "error")
        else:
            ref.update({"amount": amount, "category": category, "description": description, "date": date, "updated_at": datetime.utcnow().isoformat()})
            flash("Expense updated.", "success")
    except (ValueError, TypeError):
        flash("Enter a valid positive amount, category, and date.", "error")
    return redirect(url_for("expenses"))

@app.route("/income", methods=["GET", "POST"])
@login_required
def income():
    uid = session["user_id"]
    if request.method == "POST":
        try:
            amount = parse_amount(request.form.get("amount", ""))
            source = request.form.get("source", "Other").strip()[:80]
            date = parse_date(request.form.get("date", ""))
            if not source:
                raise ValueError("Choose an income source.")
            new_record_ref(get_store(), uid, "income").set({"amount": amount, "source": source, "date": date, "created_at": datetime.utcnow().isoformat()})
            flash(f"Added income: ₹{amount:,.2f} from {source}", "success")
        except (ValueError, TypeError):
            flash("Enter a valid positive amount, source, and date.", "error")
        except Exception:
            app.logger.warning("Could not save income to Firestore")
            flash("Could not save this income to Firestore. Please try again.", "error")
        return redirect(url_for("income"))
    rows = sorted(records(get_store(), uid, "income"), key=lambda row: (row.get("date", ""), row.get("created_at", "")), reverse=True)
    total = sum(row.get("amount", 0) for row in rows)
    return render_template("income.html", income=rows, total_income=total, user=current_user())

@app.route("/income/<income_id>/edit", methods=["POST"])
@login_required
def edit_income(income_id):
    try:
        amount = parse_amount(request.form.get("amount", ""))
        source = request.form.get("source", "Other").strip()[:80]
        date = parse_date(request.form.get("date", ""))
        ref = record_ref(get_store(), session["user_id"], "income", income_id)
        if not ref.get().exists:
            flash("Income not found.", "error")
        else:
            ref.update({"amount": amount, "source": source, "date": date, "updated_at": datetime.utcnow().isoformat()})
            flash("Income updated.", "success")
    except (ValueError, TypeError):
        flash("Enter a valid positive amount, source, and date.", "error")
    return redirect(url_for("income"))

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    uid = session["user_id"]
    month = datetime.now().strftime("%Y-%m")
    store = get_store()
    if request.method == "POST":
        category = request.form.get("category", "").strip()[:60]
        try:
            amount = parse_amount(request.form.get("amount", ""))
            if not category:
                raise ValueError("Choose a category.")
            document_id = f"{month}_{quote(category, safe='')}"
            record_ref(store, uid, "budgets", document_id).set({"category": category, "month": month, "amount": amount, "updated_at": datetime.utcnow().isoformat()})
            flash(f"Monthly limit saved for {category}.", "success")
        except (ValueError, TypeError):
            flash("Enter a category and a valid positive budget amount.", "error")
        except Exception:
            app.logger.warning("Could not save budget to Firestore")
            flash("Could not save this budget to Firestore. Please try again.", "error")
        return redirect(url_for("budget"))

    income_rows = [row for row in records(store, uid, "income") if row.get("date", "").startswith(month)]
    expense_rows = [row for row in records(store, uid, "expenses") if row.get("date", "").startswith(month)]
    budget_rows = [row for row in records(store, uid, "budgets") if row.get("month") == month]
    income = sum(row.get("amount", 0) for row in income_rows)
    expenses = sum(row.get("amount", 0) for row in expense_rows)
    category_totals = {}
    for row in expense_rows:
        category = row.get("category", "Other")
        category_totals.setdefault(category, {"category": category, "total": 0, "count": 0})
        category_totals[category]["total"] += row.get("amount", 0)
        category_totals[category]["count"] += 1
    categories = sorted(category_totals.values(), key=lambda row: row["total"], reverse=True)
    spent_by_category = {row["category"]: row["total"] for row in categories}
    category_budgets = [{
        "category": row.get("category", "Other"),
        "limit_amount": row.get("amount", 0),
        "spent": spent_by_category.get(row.get("category"), 0),
    } for row in budget_rows]
    categories_for_form = [{"category": category} for category in sorted(set(spent_by_category) | {row.get("category", "Other") for row in budget_rows})]

    balance = income - expenses
    
    # 50/30/20 Budgeting Rule Calculation
    needs_budget = round(income * 0.50, 2)
    wants_budget = round(income * 0.30, 2)
    savings_budget = round(income * 0.20, 2)
    
    return render_template(
        "budget.html",
        income=income,
        expenses=expenses,
        balance=balance,
        categories=categories,
        category_budgets=category_budgets,
        categories_for_form=categories_for_form,
        month=month,
        needs_budget=needs_budget,
        wants_budget=wants_budget,
        savings_budget=savings_budget,
        user=current_user()
    )

@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    uid = session["user_id"]
    store = get_store()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            target = parse_amount(request.form.get("target", ""))
            saved = float(request.form.get("saved", 0) or 0)
            deadline = request.form.get("deadline", "")
            if saved < 0 or not math.isfinite(saved) or not name or len(name) > 80:
                raise ValueError("Invalid goal details.")
            if deadline:
                parse_date(deadline)
            new_record_ref(store, uid, "goals").set({"name": name, "target": target, "saved": saved, "deadline": deadline, "created_at": datetime.utcnow().isoformat()})
            flash(f"Savings goal '{name}' created successfully!", "success")
        except ValueError:
            flash("Invalid numeric value for target or saved amount.", "error")
        except Exception:
            app.logger.warning("Could not save goal to Firestore")
            flash("Could not save this goal to Firestore. Please try again.", "error")
        return redirect(url_for("goals"))

    rows = sorted(records(store, uid, "goals"), key=lambda row: row.get("created_at", ""), reverse=True)
    total_target = sum(row.get("target", 0) for row in rows)
    total_saved = sum(row.get("saved", 0) for row in rows)
    return render_template("goals.html", goals=rows, total_target=total_target, total_saved=total_saved, user=current_user())

@app.route("/goals/contribute/<goal_id>", methods=["POST"])
@login_required
def contribute_goal(goal_id):
    uid = session["user_id"]
    try:
        amount = parse_amount(request.form.get("amount", ""))
        ref = record_ref(get_store(), uid, "goals", goal_id)
        snapshot = ref.get()
        if not snapshot.exists:
            flash("Goal not found.", "error")
        else:
            saved = snapshot.to_dict().get("saved", 0) + amount
            ref.update({"saved": saved, "updated_at": datetime.utcnow().isoformat()})
            flash(f"Added ₹{amount:,.2f} towards your goal!", "success")
    except (ValueError, TypeError):
        flash("Enter a valid positive contribution.", "error")
    except Exception:
        app.logger.warning("Could not update goal in Firestore")
        flash("Could not save this contribution. Please try again.", "error")
    return redirect(url_for("goals"))

@app.route("/goals/<goal_id>/edit", methods=["POST"])
@login_required
def edit_goal(goal_id):
    name = request.form.get("name", "").strip()[:80]
    deadline = request.form.get("deadline", "")
    try:
        target = parse_amount(request.form.get("target", ""))
        saved = float(request.form.get("saved", "0"))
        if not name or not math.isfinite(saved) or saved < 0:
            raise ValueError("Invalid goal details.")
        if deadline:
            parse_date(deadline)
        ref = record_ref(get_store(), session["user_id"], "goals", goal_id)
        if not ref.get().exists:
            flash("Goal not found.", "error")
        else:
            ref.update({"name": name, "target": target, "saved": saved, "deadline": deadline, "updated_at": datetime.utcnow().isoformat()})
            flash("Goal updated.", "success")
    except (ValueError, TypeError):
        flash("Enter a valid goal name, target, saved amount, and date.", "error")
    return redirect(url_for("goals"))

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    uid = session["user_id"]
    store = get_store()
    profile_ref = user_ref(store, uid)
    profile_snapshot = profile_ref.get()
    user = profile_snapshot.to_dict() if profile_snapshot.exists else None
    if user is None:
        session.clear()
        flash("Your Firebase profile could not be found. Please sign in again.", "error")
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            if not name or len(name) > 80:
                raise ValueError("Enter a valid name.")
            firebase_auth, _ = get_firebase_clients()
            firebase_auth.update_user(uid, display_name=name)
            profile_ref.set({"name": name, "updated_at": datetime.utcnow().isoformat()}, merge=True)
            session["user_name"] = name
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
        except ValueError as error:
            flash(str(error), "error")
        except Exception:
            app.logger.warning("Could not update Firebase profile")
            flash("Could not update your profile in Firebase. Please try again.", "error")
        return redirect(url_for("profile"))
    return render_template("profile.html", user={**user, "id": uid})

def recent_months(count=6):
    month = datetime.now().replace(day=1)
    months = []
    for _ in range(count):
        months.append(month.strftime("%Y-%m"))
        month = month.replace(year=month.year - 1, month=12) if month.month == 1 else month.replace(month=month.month - 1)
    return list(reversed(months))

@app.route("/analytics")
@login_required
def analytics():
    uid = session["user_id"]
    months = recent_months()
    store = get_store()
    income_rows = records(store, uid, "income")
    expense_rows = records(store, uid, "expenses")
    incomes = {month: sum(row.get("amount", 0) for row in income_rows if row.get("date", "").startswith(month)) for month in months}
    expenses = {month: sum(row.get("amount", 0) for row in expense_rows if row.get("date", "").startswith(month)) for month in months}
    total_income = sum(row.get("amount", 0) for row in income_rows)
    total_expenses = sum(row.get("amount", 0) for row in expense_rows)
    category_totals = {}
    for row in expense_rows:
        category = row.get("category", "Other")
        category_totals[category] = category_totals.get(category, 0) + row.get("amount", 0)
    categories = sorted(({"category": category, "total": total} for category, total in category_totals.items()), key=lambda row: row["total"], reverse=True)
    chart = {
        "labels": months,
        "income": [incomes.get(month, 0) for month in months],
        "expenses": [expenses.get(month, 0) for month in months],
        "categories": [row["category"] for row in categories],
        "categoryTotals": [row["total"] for row in categories],
    }
    return render_template("analytics.html", user=current_user(), chart=chart, categories=categories,
                           total_income=total_income, total_expenses=total_expenses,
                           balance=total_income - total_expenses,
                           average_monthly=sum(chart["expenses"]) / len(months),
                           top_category=categories[0] if categories else None)

@app.route("/recommendations")
@login_required
def recommendations():
    uid = session["user_id"]
    month = datetime.now().strftime("%Y-%m")
    store = get_store()
    income_rows = records(store, uid, "income")
    expense_rows = records(store, uid, "expenses")
    budgets = [row for row in records(store, uid, "budgets") if row.get("month") == month]
    goals = records(store, uid, "goals")
    income_total = sum(row.get("amount", 0) for row in income_rows if row.get("date", "").startswith(month))
    month_expenses = [row for row in expense_rows if row.get("date", "").startswith(month)]
    expense_total = sum(row.get("amount", 0) for row in month_expenses)
    category_totals = {}
    for row in month_expenses:
        category = row.get("category", "Other")
        category_totals[category] = category_totals.get(category, 0) + row.get("amount", 0)
    categories = sorted(({"category": category, "total": total} for category, total in category_totals.items()), key=lambda row: row["total"], reverse=True)
    for budget_row in budgets:
        budget_row["limit_amount"] = budget_row.get("amount", 0)
        budget_row["spent"] = category_totals.get(budget_row.get("category"), 0)
    items = []
    if income_total and expense_total > income_total:
        items.append({"title": "This month’s expenses exceed recorded income", "detail": f"Expenses are ₹{expense_total - income_total:,.2f} above income so far. Review this month’s transactions and upcoming bills.", "kind": "warning"})
    for row in budgets:
        ratio = row["spent"] / row["limit_amount"] if row["limit_amount"] else 0
        if ratio >= 0.8:
            state = "exceeded" if ratio >= 1 else "close to"
            items.append({"title": f"{row['category']} budget {state}", "detail": f"₹{row['spent']:,.2f} of ₹{row['limit_amount']:,.2f} used ({ratio * 100:.0f}%). Consider checking remaining plans in this category.", "kind": "warning" if ratio >= 1 else "notice"})
    if categories and expense_total:
        top = categories[0]
        share = top["total"] / expense_total * 100
        items.append({"title": f"{top['category']} is your largest category", "detail": f"It accounts for {share:.0f}% of this month’s recorded expenses (₹{top['total']:,.2f}). Review recent transactions to see whether any are flexible.", "kind": "insight"})
    for goal in goals:
        if goal["target"] > 0 and goal["saved"] < goal["target"]:
            remaining = goal["target"] - goal["saved"]
            items.append({"title": f"Keep building {goal['name']}", "detail": f"₹{remaining:,.2f} remains to reach this goal. Choose a regular contribution that fits your recorded monthly balance.", "kind": "goal"})
    if not items:
        items.append({"title": "Not enough activity for tailored insights", "detail": "Record income, expenses, or a category budget to see observations based on your own data.", "kind": "insight"})
    return render_template("recommendations.html", user=current_user(), recommendations=items,
                           month=month, income=income_total, expenses=expense_total,
                           balance=income_total - expense_total)

@app.route("/ai")
@login_required
def ai():
    return render_template("ai-assistant.html", user=current_user(), ai_available=bool(os.getenv("GEMINI_API_KEY")))

def finance_context(uid):
    store = get_store()
    income_sources = records(store, uid, "income")
    expense_rows = records(store, uid, "expenses")
    goals = records(store, uid, "goals")
    month = datetime.now().strftime("%Y-%m")
    income = sum(row.get("amount", 0) for row in income_sources)
    expenses = sum(row.get("amount", 0) for row in expense_rows)
    monthly_income = sum(row.get("amount", 0) for row in income_sources if row.get("date", "").startswith(month))
    monthly_expenses = sum(row.get("amount", 0) for row in expense_rows if row.get("date", "").startswith(month))
    category_totals = {}
    for row in expense_rows:
        category = row.get("category", "Other")
        category_totals.setdefault(category, {"category": category, "total": 0, "count": 0})
        category_totals[category]["total"] += row.get("amount", 0)
        category_totals[category]["count"] += 1
    cats = sorted(category_totals.values(), key=lambda row: row["total"], reverse=True)
    recent = sorted(expense_rows, key=lambda row: (row.get("date", ""), row.get("created_at", "")), reverse=True)[:8]
    income_sources = sorted(income_sources, key=lambda row: row.get("date", ""), reverse=True)[:5]
    budgets = [row for row in records(store, uid, "budgets") if row.get("month") == month]
    return income, expenses, monthly_income, monthly_expenses, cats, recent, goals, income_sources, budgets

@app.route("/api/ai", methods=["POST"])
@login_required
def ai_api():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"reply": "Please enter a question or select a quick topic."}), 400

    uid = session["user_id"]
    income, expenses, monthly_income, monthly_expenses, categories, recent, goals, income_sources, budgets = finance_context(uid)
    balance = income - expenses
    
    category_summary = "\n".join([f"- {r['category']}: ₹{r['total']:,.2f} ({r['count']} transactions)" for r in categories]) or "No expenses logged yet."
    recent_transactions = "\n".join([f"- {r['date']} | {r['category']}: ₹{r['amount']:,.2f} ({r['description'] or 'No description'})" for r in recent]) or "No recent transactions."
    goals_summary = "\n".join([f"- {g['name']}: ₹{g['saved']:,.2f} saved out of ₹{g['target']:,.2f} (Target Date: {g['deadline'] or 'N/A'})" for g in goals]) or "No savings goals set yet."
    income_summary = "\n".join([f"- {i['date']} | {i['source']}: ₹{i['amount']:,.2f}" for i in income_sources]) or "No income recorded."
    budget_summary = "\n".join([f"- {b['category']}: ₹{b['amount']:,.2f} limit" for b in budgets]) or "No monthly category budgets set."

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"reply": "AI assistant is temporarily unavailable. Please check your Gemini API configuration."}), 503
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        prompt = f"""You are PocketSmart AI, a practical personal finance assistant, not a licensed financial adviser.
Use the user's real records to answer carefully and concisely. Avoid guarantees and regulated investment advice.

=== USER FINANCIAL PROFILE ===
- Total Income: ₹{income:,.2f}
- Total Expenses: ₹{expenses:,.2f}
- Current Net Balance: ₹{balance:,.2f}
- This Month Income: ₹{monthly_income:,.2f}
- This Month Expenses: ₹{monthly_expenses:,.2f}
- Savings Rate: {round((balance / income * 100), 1) if income > 0 else 0}%

=== INCOME SOURCES ===
{income_summary}

=== EXPENSE BREAKDOWN BY CATEGORY ===
{category_summary}

=== RECENT EXPENSES ===
{recent_transactions}

=== SAVINGS GOALS ===
{goals_summary}

=== CURRENT MONTH CATEGORY BUDGETS ===
{budget_summary}

=== INSTRUCTIONS ===
1. Use Indian Rupee (₹) for all currency figures.
2. Format your response cleanly using Markdown (bold key amounts, use bullet points, clear subheadings where helpful).
3. Directly reference the user's real financial metrics when answering. Give realistic, encouraging, and actionable recommendations.
4. If the user asks for spending optimization, point out their highest expense category and give 2-3 specific money-saving tips.
5. If the user asks about savings goals, calculate how much they need per month or how their current balance can help achieve them.
6. Keep the tone professional, friendly, motivating, and concise.

User Question: {message}
"""
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=1000),
        )
        if response and response.text:
            return jsonify({"reply": response.text, "source": "gemini", "model": model_name})
    except Exception:
        app.logger.warning("Gemini request failed for user id %s", uid)
    return jsonify({"reply": "AI assistant is temporarily unavailable. Please check your Gemini API configuration and try again."}), 503

@app.route("/api/delete-expense/<expense_id>", methods=["DELETE", "POST"])
@login_required
def delete_expense(expense_id):
    uid = session["user_id"]
    ref = record_ref(get_store(), uid, "expenses", expense_id)
    deleted = ref.get().exists
    if deleted:
        ref.delete()
    if request.is_json or request.method == "DELETE":
        return jsonify({"success": deleted, "message": "Expense deleted" if deleted else "Expense not found"}), 200 if deleted else 404
    flash("Expense deleted successfully." if deleted else "Expense not found.", "info" if deleted else "error")
    return redirect(url_for("expenses"))

@app.route("/api/delete-income/<income_id>", methods=["DELETE", "POST"])
@login_required
def delete_income(income_id):
    uid = session["user_id"]
    ref = record_ref(get_store(), uid, "income", income_id)
    deleted = ref.get().exists
    if deleted:
        ref.delete()
    if request.is_json or request.method == "DELETE":
        return jsonify({"success": deleted, "message": "Income deleted" if deleted else "Income not found"}), 200 if deleted else 404
    flash("Income deleted." if deleted else "Income not found.", "info" if deleted else "error")
    return redirect(url_for("income"))

@app.route("/api/delete-goal/<goal_id>", methods=["DELETE", "POST"])
@login_required
def delete_goal(goal_id):
    uid = session["user_id"]
    ref = record_ref(get_store(), uid, "goals", goal_id)
    deleted = ref.get().exists
    if deleted:
        ref.delete()
    if request.is_json or request.method == "DELETE":
        return jsonify({"success": deleted, "message": "Goal deleted" if deleted else "Goal not found"}), 200 if deleted else 404
    flash("Goal removed." if deleted else "Goal not found.", "info" if deleted else "error")
    return redirect(url_for("goals"))

@app.route("/api/chart-data")
@login_required
def chart_data():
    uid = session["user_id"]
    months = recent_months()
    income_rows = records(get_store(), uid, "income")
    expense_rows = records(get_store(), uid, "expenses")
    expense_map = {month: sum(row.get("amount", 0) for row in expense_rows if row.get("date", "").startswith(month)) for month in months}
    income_map = {month: sum(row.get("amount", 0) for row in income_rows if row.get("date", "").startswith(month)) for month in months}
    current_month = datetime.now().strftime("%Y-%m")
    category_totals = {}
    for row in expense_rows:
        if row.get("date", "").startswith(current_month):
            category = row.get("category", "Other")
            category_totals[category] = category_totals.get(category, 0) + row.get("amount", 0)
    categories = sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
    lifetime_income = sum(row.get("amount", 0) for row in income_rows)
    lifetime_expenses = sum(row.get("amount", 0) for row in expense_rows)
    return jsonify({
        "categories": [category for category, _ in categories],
        "categoryTotals": [total for _, total in categories],
        "months": months,
        "monthlyTotals": [expense_map.get(month, 0) for month in months],
        "monthlyIncome": [income_map.get(month, 0) for month in months],
        "totalIncome": lifetime_income,
        "totalExpenses": lifetime_expenses,
        "balance": lifetime_income - lifetime_expenses
    })

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", port=5000)
