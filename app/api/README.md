# Project Folder Naming Convention

This document describes the naming standards used for both the **Streamlit frontend** and the **API (Lambda) backend** in this project.  
The goal is to keep file and folder names **predictable, REST-like, and consistent**.

---

## 🔹 API (Lambda) Functions

Each Lambda function folder should follow the format:

<http-method>_<table-name>

markdown
Copy code

- **`http-method`** → one of: `get`, `post`, `put`, `delete`
- **`table-name`** → lowercase, matches the logical database table/entity the function operates on

### Examples:
functions/
├── get_users/ # Fetch user(s) from users table
├── post_users/ # Create new user in users table
├── get_portfolio/ # Fetch portfolio data
├── post_transactions/ # Insert new transaction
└── delete_watchlist/ # Remove a stock from watchlist

perl
Copy code

Inside each folder:
get_users/
├── handler.py
└── requirements.txt # (optional if extra deps needed)

yaml
Copy code

---

## 🔹 Streamlit Frontend

Streamlit pages and API client functions should also follow the **same convention** so it’s obvious which backend they map to.

### Pages (`/frontend/pages/`)
pages/
├── get_users.py
├── post_users.py
├── get_portfolio.py
└── post_transactions.py

python
Copy code

### API Client (`/frontend/utils/api_client.py`)
Define one function per API, named using the same convention:

```python
from utils.request import api_get, api_post

def get_users(user_id: str):
    return api_get("/users", params={"id": user_id})

def post_users(payload: dict):
    return api_post("/users", json=payload)

def get_portfolio(user_id: str):
    return api_get("/portfolio", params={"id": user_id})
🔹 Benefits of This Convention
Consistency → Frontend and backend naming mirrors HTTP verbs + tables.

Discoverability → Easy to locate API functions and their corresponding frontend usage.

Scalability → Supports new tables/entities without ambiguity.

Alignment with REST → Naming reflects standard RESTful API design.

🔹 Summary
Backend (Lambda functions):

functions/get_<table>/

functions/post_<table>/

Frontend (Streamlit pages & utils):

pages/get_<table>.py

pages/post_<table>.py

api_client.py functions: get_<table>(), post_<table>()

css
Copy code
get_<table>
post_<table>
put_<table>
delete_<table>
Use lowercase and underscores (_) only.
Avoid plural/singular mismatch → always match your table name.

yaml
Copy code

---

Do you want me to also include a **sample folder tree diagram** (frontend + backend together) using this convention?







Ask ChatGPT
