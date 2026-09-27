from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import sqlite3
import os
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "pocketsmart-secure-key-2026-v2")
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
DB = os.path.join(DB_DIR, "pocketsmart.db")
os.makedirs(DB_DIR, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        date TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS income (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        source TEXT NOT NULL,
        date TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        target REAL NOT NULL,
        saved REAL DEFAULT 0,
        deadline TEXT
    )""")
    # Ensure deadline column exists if db was created with older schema
    try:
        conn.execute("ALTER TABLE goals ADD COLUMN deadline TEXT")
    except sqlite3.OperationalError:
        pass # already exists
    conn.commit()

    # Create demo user if not exists
    demo = conn.execute("SELECT id FROM users WHERE email='demo@pocketsmart.ai'").fetchone()
    if not demo:
        cur = conn.execute(
            "INSERT INTO users (name, email, password, created_at) VALUES (?, ?, ?, ?)",
            ("Demo User", "demo@pocketsmart.ai", generate_password_hash("demo123"), datetime.now().isoformat())
        )
        demo_id = cur.lastrowid
        # Seed realistic sample data
        sample_income = [
            (demo_id, 65000.0, "Monthly Salary", "2026-09-01"),
            (demo_id, 12000.0, "Freelance Project", "2026-09-15")
        ]
        for inc in sample_income:
            conn.execute("INSERT INTO income (user_id, amount, source, date) VALUES (?, ?, ?, ?)", inc)

        sample_expenses = [
            (demo_id, 18000.0, "Rent & Housing", "Apartment rent for September", "2026-09-02"),
            (demo_id, 7500.0, "Groceries & Food", "Supermarket and weekly vegetables", "2026-09-05"),
            (demo_id, 3200.0, "Utilities & Bills", "Electricity & High-speed Wifi", "2026-09-08"),
            (demo_id, 4500.0, "Dining & Outing", "Weekend dinners with friends", "2026-09-12"),
            (demo_id, 2800.0, "Transportation", "Fuel & Metro passes", "2026-09-18"),
            (demo_id, 3500.0, "Shopping & Misc", "Clothing and household supplies", "2026-09-22")
        ]
        for exp in sample_expenses:
            conn.execute("INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)", exp)

        sample_goals = [
            (demo_id, "Emergency Fund", 100000.0, 45000.0, "2026-12-31"),
            (demo_id, "New Laptop", 75000.0, 35000.0, "2026-11-30"),
            (demo_id, "Vacation Trip", 40000.0, 15000.0, "2027-02-15")
        ]
        for g in sample_goals:
            conn.execute("INSERT INTO goals (user_id, name, target, saved, deadline) VALUES (?, ?, ?, ?, ?)", g)

        conn.commit()

    conn.close()

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access this page.", "info")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def current_user():
    if "user_id" not in session:
        return None
    conn = get_db()
    user = conn.execute("SELECT id, name, email, created_at FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return user

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
            return render_template("signup.html", name=name, email=email)
        if password != confirm:
            flash("Passwords do not match. Please re-enter.", "error")
            return render_template("signup.html", name=name, email=email)
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("signup.html", name=name, email=email)

        conn = get_db()
        try:
            cur = conn.execute(
                "INSERT INTO users (name, email, password, created_at) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), datetime.now().isoformat())
            )
            user_id = cur.lastrowid

            # Seed a welcoming starter income and goal for the new user
            conn.execute("INSERT INTO income (user_id, amount, source, date) VALUES (?, ?, ?, ?)",
                         (user_id, 50000.0, "Monthly Salary", datetime.now().strftime("%Y-%m-%d")))
            conn.execute("INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)",
                         (user_id, 4500.0, "Groceries & Food", "Initial grocery shopping", datetime.now().strftime("%Y-%m-%d")))
            conn.execute("INSERT INTO goals (user_id, name, target, saved, deadline) VALUES (?, ?, ?, ?, ?)",
                         (user_id, "Emergency Fund", 50000.0, 10000.0, "2026-12-31"))

            conn.commit()
            session["user_id"] = user_id
            session["user_name"] = name
            flash(f"Welcome to PocketSmart AI, {name}! Your account is ready.", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("An account with this email already exists. Please log in.", "error")
            return redirect(url_for("login"))
        finally:
            conn.close()

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        
        flash("Invalid email or password. Please check your credentials.", "error")
    return render_template("login.html")

@app.route("/demo-login")
def demo_login():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email='demo@pocketsmart.ai'").fetchone()
    conn.close()
    if user:
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        flash("Logged in with Demo Account! Explore all features freely.", "success")
        return redirect(url_for("dashboard"))
    flash("Demo account not found.", "error")
    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    conn = get_db()
    income = conn.execute("SELECT COALESCE(SUM(amount), 0) total FROM income WHERE user_id=?", (uid,)).fetchone()["total"]
    expenses = conn.execute("SELECT COALESCE(SUM(amount), 0) total FROM expenses WHERE user_id=?", (uid,)).fetchone()["total"]
    balance = income - expenses
    
    categories = conn.execute("""
        SELECT category, SUM(amount) total, COUNT(*) count 
        FROM expenses 
        WHERE user_id=? 
        GROUP BY category 
        ORDER BY total DESC
    """, (uid,)).fetchall()
    
    recent_expenses = conn.execute("""
        SELECT * FROM expenses 
        WHERE user_id=? 
        ORDER BY date DESC, id DESC 
        LIMIT 6
    """, (uid,)).fetchall()
    
    recent_income = conn.execute("""
        SELECT * FROM income 
        WHERE user_id=? 
        ORDER BY date DESC, id DESC 
        LIMIT 4
    """, (uid,)).fetchall()
    
    goals = conn.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC LIMIT 4", (uid,)).fetchall()
    conn.close()

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
    conn = get_db()
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", 0))
            category = request.form.get("category", "Other").strip()
            description = request.form.get("description", "").strip()
            date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
            
            if amount <= 0:
                flash("Please enter a valid expense amount greater than 0.", "error")
            else:
                conn.execute(
                    "INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)",
                    (uid, amount, category, description, date)
                )
                conn.commit()
                flash(f"Added expense: ₹{amount:,.2f} for {category}", "success")
        except ValueError:
            flash("Invalid amount format.", "error")
        return redirect(url_for("expenses"))

    rows = conn.execute("SELECT * FROM expenses WHERE user_id=? ORDER BY date DESC, id DESC", (uid,)).fetchall()
    total_spent = conn.execute("SELECT COALESCE(SUM(amount), 0) total FROM expenses WHERE user_id=?", (uid,)).fetchone()["total"]
    categories = conn.execute("SELECT category, SUM(amount) total FROM expenses WHERE user_id=? GROUP BY category ORDER BY total DESC", (uid,)).fetchall()
    conn.close()
    return render_template("expenses.html", expenses=rows, total_spent=total_spent, categories=categories, user=current_user())

@app.route("/income", methods=["POST"])
@login_required
def add_income():
    uid = session["user_id"]
    try:
        amount = float(request.form.get("amount", 0))
        source = request.form.get("source", "Salary").strip()
        date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
        if amount <= 0:
            flash("Please enter a valid income amount greater than 0.", "error")
        else:
            conn = get_db()
            conn.execute("INSERT INTO income (user_id, amount, source, date) VALUES (?, ?, ?, ?)", (uid, amount, source, date))
            conn.commit()
            conn.close()
            flash(f"Added income: ₹{amount:,.2f} from {source}", "success")
    except ValueError:
        flash("Invalid income amount.", "error")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/budget")
@login_required
def budget():
    uid = session["user_id"]
    conn = get_db()
    income = conn.execute("SELECT COALESCE(SUM(amount), 0) total FROM income WHERE user_id=?", (uid,)).fetchone()["total"]
    expenses = conn.execute("SELECT COALESCE(SUM(amount), 0) total FROM expenses WHERE user_id=?", (uid,)).fetchone()["total"]
    categories = conn.execute("""
        SELECT category, SUM(amount) total, COUNT(*) count
        FROM expenses 
        WHERE user_id=? 
        GROUP BY category 
        ORDER BY total DESC
    """, (uid,)).fetchall()
    conn.close()
    
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
        needs_budget=needs_budget,
        wants_budget=wants_budget,
        savings_budget=savings_budget,
        user=current_user()
    )

@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    uid = session["user_id"]
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            target = float(request.form.get("target", 0))
            saved = float(request.form.get("saved", 0))
            deadline = request.form.get("deadline", "")
            if not name or target <= 0:
                flash("Please provide a valid goal name and target amount.", "error")
            else:
                conn.execute(
                    "INSERT INTO goals (user_id, name, target, saved, deadline) VALUES (?, ?, ?, ?, ?)",
                    (uid, name, target, saved, deadline)
                )
                conn.commit()
                flash(f"Savings goal '{name}' created successfully!", "success")
        except ValueError:
            flash("Invalid numeric value for target or saved amount.", "error")
        return redirect(url_for("goals"))

    rows = conn.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    total_target = sum(r["target"] for r in rows)
    total_saved = sum(r["saved"] for r in rows)
    conn.close()
    return render_template("goals.html", goals=rows, total_target=total_target, total_saved=total_saved, user=current_user())

@app.route("/goals/contribute/<int:goal_id>", methods=["POST"])
@login_required
def contribute_goal(goal_id):
    uid = session["user_id"]
    try:
        amount = float(request.form.get("amount", 0))
        if amount > 0:
            conn = get_db()
            conn.execute("UPDATE goals SET saved = saved + ? WHERE id=? AND user_id=?", (amount, goal_id, uid))
            conn.commit()
            conn.close()
            flash(f"Added ₹{amount:,.2f} towards your goal!", "success")
    except Exception as e:
        flash("Failed to add contribution.", "error")
    return redirect(url_for("goals"))

@app.route("/ai")
@login_required
def ai():
    return render_template("ai-assistant.html", user=current_user())

def finance_context(uid):
    conn = get_db()
    income = conn.execute("SELECT COALESCE(SUM(amount), 0) total FROM income WHERE user_id=?", (uid,)).fetchone()["total"]
    expenses = conn.execute("SELECT COALESCE(SUM(amount), 0) total FROM expenses WHERE user_id=?", (uid,)).fetchone()["total"]
    cats = conn.execute("SELECT category, SUM(amount) total, COUNT(*) count FROM expenses WHERE user_id=? GROUP BY category ORDER BY total DESC", (uid,)).fetchall()
    recent = conn.execute("SELECT amount, category, description, date FROM expenses WHERE user_id=? ORDER BY date DESC LIMIT 8", (uid,)).fetchall()
    goals = conn.execute("SELECT name, target, saved, deadline FROM goals WHERE user_id=?", (uid,)).fetchall()
    income_sources = conn.execute("SELECT amount, source, date FROM income WHERE user_id=? ORDER BY date DESC LIMIT 5", (uid,)).fetchall()
    conn.close()
    return income, expenses, cats, recent, goals, income_sources

@app.route("/api/ai", methods=["POST"])
@login_required
def ai_api():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"reply": "Please enter a question or select a quick topic."}), 400

    uid = session["user_id"]
    income, expenses, categories, recent, goals, income_sources = finance_context(uid)
    balance = income - expenses
    
    category_summary = "\n".join([f"- {r['category']}: ₹{r['total']:,.2f} ({r['count']} transactions)" for r in categories]) or "No expenses logged yet."
    recent_transactions = "\n".join([f"- {r['date']} | {r['category']}: ₹{r['amount']:,.2f} ({r['description'] or 'No description'})" for r in recent]) or "No recent transactions."
    goals_summary = "\n".join([f"- {g['name']}: ₹{g['saved']:,.2f} saved out of ₹{g['target']:,.2f} (Target Date: {g['deadline'] or 'N/A'})" for g in goals]) or "No savings goals set yet."
    income_summary = "\n".join([f"- {i['date']} | {i['source']}: ₹{i['amount']:,.2f}" for i in income_sources]) or "No income recorded."

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key)
            
            prompt = f"""You are PocketSmart AI, an intelligent, empathetic, and highly practical personal financial advisor and budgeting coach.
Your job is to provide accurate, actionable, data-driven financial advice based on the user's REAL financial records provided below.

=== USER FINANCIAL PROFILE ===
- Total Income: ₹{income:,.2f}
- Total Expenses: ₹{expenses:,.2f}
- Current Net Balance: ₹{balance:,.2f}
- Savings Rate: {round((balance / income * 100), 1) if income > 0 else 0}%

=== INCOME SOURCES ===
{income_summary}

=== EXPENSE BREAKDOWN BY CATEGORY ===
{category_summary}

=== RECENT EXPENSES ===
{recent_transactions}

=== SAVINGS GOALS ===
{goals_summary}

=== INSTRUCTIONS ===
1. Use Indian Rupee (₹) for all currency figures.
2. Format your response cleanly using Markdown (bold key amounts, use bullet points, clear subheadings where helpful).
3. Directly reference the user's real financial metrics when answering. Give realistic, encouraging, and actionable recommendations.
4. If the user asks for spending optimization, point out their highest expense category and give 2-3 specific money-saving tips.
5. If the user asks about savings goals, calculate how much they need per month or how their current balance can help achieve them.
6. Keep the tone professional, friendly, motivating, and concise.

User Question: {message}
"""
            # Candidate models in order of preference
            candidate_models = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.7-flash"]
            for model_name in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.3,
                            max_output_tokens=1000
                        )
                    )
                    if response and response.text:
                        return jsonify({"reply": response.text, "source": "gemini", "model": model_name})
                except Exception as model_err:
                    print(f"Model {model_name} error: {model_err}")
                    continue

        except Exception as e:
            print("Gemini Client Error:", e)

    # Smart local algorithmic fallback if Gemini fails or is unreachable
    top_cat = categories[0] if categories else None
    savings_ratio = (balance / income * 100) if income > 0 else 0

    if "save" in message.lower() or "saving" in message.lower() or "goal" in message.lower():
        reply = f"""### 💡 Savings Analysis & Advice

- **Current Balance:** ₹{balance:,.2f}
- **Income:** ₹{income:,.2f}
- **Current Savings Rate:** {savings_ratio:.1f}%

**Recommendations:**
1. **50/30/20 Strategy:** Aim to allocate 20% of your income (**₹{max(income * 0.20, 0):,.2f}**) straight into savings/investments.
2. **Emergency Fund:** Ensure you keep at least 3-6 months of basic expenses (**₹{max(expenses * 3, 30000):,.2f}**) as a safety buffer.
3. Check your **Goals** tab to set a targeted deadline and automate small weekly transfers!"""
    elif "spend" in message.lower() or "expense" in message.lower() or "cut" in message.lower():
        top_info = f"Your highest expense category is **{top_cat['category']}** at **₹{top_cat['total']:,.2f}**." if top_cat else "You haven't logged any expenses yet."
        reply = f"""### 📊 Spending & Expense Breakdown

- **Total Spent:** ₹{expenses:,.2f}
- **Total Income:** ₹{income:,.2f}
- **Remaining Balance:** ₹{balance:,.2f}

{top_info}

**Actionable Steps to Cut Costs:**
1. Review transactions in **{top_cat['category'] if top_cat else 'Expenses'}** and see if non-essential items can be trimmed by 10-15%.
2. Track daily discretionary spending before purchasing impulse items.
3. Compare utility and subscription bills regularly to eliminate unused services."""
    else:
        reply = f"""### 💰 PocketSmart Financial Overview

- **Income:** ₹{income:,.2f}
- **Expenses:** ₹{expenses:,.2f}
- **Net Balance:** ₹{balance:,.2f}
- **Active Savings Goals:** {len(goals)}

Feel free to ask me anything specific like:
* *"Where am I spending too much?"*
* *"How can I save ₹20,000 in 3 months?"*
* *"Give me a customized 50/30/20 budget plan."*"""

    return jsonify({"reply": reply, "source": "local"})

@app.route("/api/delete-expense/<int:expense_id>", methods=["DELETE", "POST"])
@login_required
def delete_expense(expense_id):
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (expense_id, session["user_id"]))
    conn.commit()
    conn.close()
    if request.is_json or request.method == "DELETE":
        return jsonify({"success": True, "message": "Expense deleted"})
    flash("Expense deleted successfully.", "info")
    return redirect(url_for("expenses"))

@app.route("/api/delete-goal/<int:goal_id>", methods=["DELETE", "POST"])
@login_required
def delete_goal(goal_id):
    conn = get_db()
    conn.execute("DELETE FROM goals WHERE id=? AND user_id=?", (goal_id, session["user_id"]))
    conn.commit()
    conn.close()
    if request.is_json or request.method == "DELETE":
        return jsonify({"success": True, "message": "Goal deleted"})
    flash("Goal removed.", "info")
    return redirect(url_for("goals"))

@app.route("/api/chart-data")
@login_required
def chart_data():
    uid = session["user_id"]
    conn = get_db()
    cats = conn.execute("SELECT category, SUM(amount) total FROM expenses WHERE user_id=? GROUP BY category ORDER BY total DESC", (uid,)).fetchall()
    monthly = conn.execute("SELECT strftime('%Y-%m', date) month, SUM(amount) total FROM expenses WHERE user_id=? GROUP BY month ORDER BY month ASC LIMIT 6", (uid,)).fetchall()
    conn.close()
    return jsonify({
        "categories": [c["category"] for c in cats],
        "categoryTotals": [c["total"] for c in cats],
        "months": [m["month"] for m in monthly],
        "monthlyTotals": [m["total"] for m in monthly]
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
