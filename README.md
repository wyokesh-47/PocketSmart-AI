# 💰 PocketSmart AI (V2)

**PocketSmart AI** is a modern, full-featured Personal Finance Management and Budgeting Assistant powered by **Flask**, **SQLite**, and **Google Gemini AI**.

---

## ✨ Features

- 🔐 **User Authentication:** Multi-user support with secure registration, login, session management, and password hashing (Werkzeug).
- ⚡ **1-Click Instant Demo:** Quick test access with pre-populated financial data.
- 📊 **Dynamic Analytics & Charts:** Interactive Doughnut & Pie charts (Chart.js) breaking down monthly expenses and categories.
- ⚖️ **50/30/20 Smart Budgeting:** Automatic calculation of Needs (50%), Wants (30%), and Savings (20%) based on total income.
- 💸 **Expense & Income Tracking:** Add, filter, categorize, and delete expenses (Food, Rent, Utilities, Transport, Dining, Shopping, Healthcare, etc.).
- 🎯 **Savings Goals Tracker:** Set targets, track progress bars, and make quick fund contributions with deadline milestones.
- 🤖 **Gemini AI Financial Coach:** Real-time conversational AI coach analyzing actual income, spending patterns, categories, and savings goals in Indian Rupees (₹).

---

## 🛠️ Tech Stack

- **Backend:** Python 3, Flask
- **Database:** SQLite3
- **AI Integration:** Google GenAI SDK (`google-genai` / Gemini 3 Flash & 2.5 Flash)
- **Frontend:** HTML5, CSS3 (Modern Glassmorphism Dark UI), Chart.js, FontAwesome 6, Marked.js

---

## 🚀 Quick Setup & Installation

### 1. Clone the repository:
```bash
git clone https://github.com/wyokesh-47/PocketSmart-AI.git
cd PocketSmart-AI
```

### 2. Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Setup Environment Variables:
Copy `.env.example` to `.env`:
```bash
copy .env.example .env
```
Add your Gemini API Key in `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
SECRET_KEY=your_secret_key_here
```
*(Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/))*

### 4. Run the Application:
```bash
python app.py
```

### 5. Open in Browser:
Navigate to: **http://127.0.0.1:5000**

---

## 📁 Project Structure

```
PocketSmart-AI/
├── database/            # SQLite database storage
├── static/
│   ├── css/
│   │   └── style.css    # Modern Dark Theme & Glassmorphism UI
│   └── js/
├── templates/
│   ├── index.html       # Landing Page
│   ├── login.html       # Login Page
│   ├── signup.html      # Registration Page
│   ├── dashboard.html   # Main Financial Dashboard & Charts
│   ├── expenses.html    # Expenses Management
│   ├── budget.html      # 50/30/20 Budget Analytics
│   ├── goals.html       # Savings Goals Tracker
│   └── ai-assistant.html# Gemini AI Financial Coach
├── .env.example         # Environment template
├── .gitignore           # Git ignore rules
├── app.py               # Flask backend & Gemini AI API
├── README.md            # Documentation
└── requirements.txt     # Python dependencies
```
