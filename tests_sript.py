#!/usr/bin/env python3
"""
FBR POS Platform — API Test Runner
------------------------------------
Python port of the "FBR POS Platform — Complete API" Postman collection.
Runs every request end-to-end, chains variables (tokens, IDs) between
steps automatically, and prints PASS/FAIL for each check.

Setup:
    pip install requests

Run:
    python fbr_api_test_runner.py

Edit the CONFIG block below before running.
"""

import json
import sys
import time

import requests

# ============================================================
# CONFIG — edit these before running
# ============================================================
BASE_URL = "http://127.0.0.1:8000"

ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"

OWNER_EMAIL = "owner@gmail.com"
OWNER_PASSWORD = "owner123"
# ============================================================

state = {
    "ADMIN_TOKEN": None,
    "ADMIN_REFRESH": None,
    "OWNER_TOKEN": None,
    "OWNER_REFRESH": None,
    "COMPANY_ID": 1,
    "PRODUCT_ID": 1,
    "CATEGORY_ID": 1,
    "CUSTOMER_ID": 1,
    "SALE_ID": 1,
    "PLAN_ID": 1,
    "SUBSCRIPTION_ID": 1,
    "CASH_SESSION_ID": 1,
    "ORIGINAL_LINE_ID": 1,
    "CASHIER_ID": 2,
}

PASS = 0
FAIL = 0
FAILED_TESTS = []


class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def section(title):
    print(f"\n{C.BLUE}{C.BOLD}=== {title} ==={C.END}")


def jbody(r):
    try:
        return r.json()
    except ValueError:
        return {}


def show(label, r):
    body = json.dumps(jbody(r))
    print(f"  {C.YELLOW}→{C.END} {label}: {r.status_code} {body[:250]}")


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"    {C.GREEN}✓ PASS{C.END} {label}")
    else:
        FAIL += 1
        FAILED_TESTS.append(label)
        print(f"    {C.RED}✗ FAIL{C.END} {label}")


def req(method, path, token=None, json_body=None, params=None, label=""):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.request(method, url, headers=headers, json=json_body, params=params, timeout=15)
    except requests.exceptions.RequestException as e:
        global FAIL
        FAIL += 1
        msg = f"{label or path} (connection error: {e})"
        FAILED_TESTS.append(msg)
        print(f"  {C.RED}✗ Could not reach {url} — {e}{C.END}")
        return None
    show(label or f"{method} {path}", r)
    return r


def skip(reason):
    print(f"  {C.YELLOW}⚠ Skipped — {reason}{C.END}")


# ============================================================
# 01 — Authentication (split: login happens where the account exists)
# ============================================================
def step_login_admin():
    section("Login — Admin")
    r = req("POST", "/api/auth/login/",
            json_body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            label="Login as Admin")
    if r is None:
        return
    check("status 200", r.status_code == 200)
    data = jbody(r)
    check("access token received", isinstance(data.get("access"), str))
    check("role is admin", data.get("user", {}).get("role") == "admin")
    state["ADMIN_TOKEN"] = data.get("access")
    state["ADMIN_REFRESH"] = data.get("refresh")
    if not state["ADMIN_TOKEN"]:
        print(f"  {C.YELLOW}⚠ No admin token — admin-only steps below will be skipped.{C.END}")


def step_admin_profile():
    section("Get My Profile (Admin)")
    if not state["ADMIN_TOKEN"]:
        return skip("no admin token")
    r = req("GET", "/api/me/", token=state["ADMIN_TOKEN"], label="Get My Profile")
    if r is None:
        return
    check("status 200", r.status_code == 200)
    check("has email field", "email" in jbody(r))


# ============================================================
# 02 — Company Management
# ============================================================
def step_company_management():
    section("Company Management")
    if not state["ADMIN_TOKEN"]:
        return skip("no admin token")

    body = {
        "business_name": "ABC General Store",
        "ntn": "7000001",
        "strn": "3177777777777",
        "owner_cnic": "35202-1234567-1",
        "business_mode": "both",
        "fbr_business_nature": ["retailer"],
        "fbr_sector": "all_other",
        "vertical": "general_store",
        "address": "123 Main Bazaar, Lahore, Punjab",
        "phone": "0300-1234567",
        "email": "abc@store.pk",
        "subscription_plan": "trial",
        "subscription_status": "trial",
    }
    r = req("POST", "/api/companies/", token=state["ADMIN_TOKEN"], json_body=body, label="Create Company")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        if data.get("id"):
            state["COMPANY_ID"] = data["id"]
        elif r.status_code != 201:
            # Creation failed (already exists, 500, etc.) — fall back to an
            # existing company so the rest of the run isn't blocked on a bad ID.
            lr = req("GET", "/api/companies/", token=state["ADMIN_TOKEN"],
                      label="(fallback) look up existing company")
            if lr is not None and lr.status_code == 200:
                results = jbody(lr).get("results", [])
                if results:
                    state["COMPANY_ID"] = results[0]["id"]
                    print(f"  {C.YELLOW}↳ Falling back to existing company id={state['COMPANY_ID']}{C.END}")

    r = req("GET", "/api/companies/", token=state["ADMIN_TOKEN"], label="List All Companies")
    if r is not None:
        check("status 200", r.status_code == 200)
        check("results is a list", isinstance(jbody(r).get("results"), list))

    r = req("GET", f"/api/companies/{state['COMPANY_ID']}/", token=state["ADMIN_TOKEN"], label="Get Company Detail")
    if r is not None:
        check("status 200", r.status_code == 200)

    r = req("PATCH", f"/api/companies/{state['COMPANY_ID']}/modules/", token=state["ADMIN_TOKEN"],
            json_body={"module_inventory": True, "module_returns": True,
                       "module_debit_credit_notes": True, "module_basic_reports": True},
            label="Update Company Modules")
    if r is not None:
        check("status 200", r.status_code == 200)

    r = req("POST", f"/api/companies/{state['COMPANY_ID']}/activate/", token=state["ADMIN_TOKEN"],
            label="Activate Company")
    if r is not None:
        check("status 200/204", r.status_code in (200, 204))


# ============================================================
# 03 — User Management
# ============================================================
def step_create_owner():
    section("Create Owner for Company")
    if not state["ADMIN_TOKEN"]:
        return skip("no admin token")

    body = {
        "email": OWNER_EMAIL,
        "first_name": "Ahmed",
        "last_name": "Khan",
        "phone": "0300-1234567",
        "company": state["COMPANY_ID"],
        "password": OWNER_PASSWORD,
        "confirm_password": OWNER_PASSWORD,
    }
    r = req("POST", "/api/owners/", token=state["ADMIN_TOKEN"], json_body=body, label="Create Owner")
    if r is None:
        return
    check("status 201", r.status_code == 201)
    if r.status_code == 201:
        check("role is owner", jbody(r).get("role") == "owner")
    else:
        print(f"  {C.YELLOW}⚠ Owner may already exist from a previous run — that's fine.{C.END}")


def step_login_owner():
    section("Login — Owner")
    r = req("POST", "/api/auth/login/",
            json_body={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
            label="Login as Owner")
    if r is None:
        return
    check("status 200", r.status_code == 200)
    data = jbody(r)
    check("role is owner", data.get("user", {}).get("role") == "owner")
    state["OWNER_TOKEN"] = data.get("access")
    state["OWNER_REFRESH"] = data.get("refresh")
    if not state["OWNER_TOKEN"]:
        print(f"  {C.YELLOW}⚠ No owner token — owner-only steps below will be skipped.{C.END}")


def step_user_management_rest():
    section("Cashier Creation & Permissions")
    if not state["OWNER_TOKEN"]:
        return skip("no owner token")

    body = {
        "email": "cashier1@abcstore.pk",
        "first_name": "Ali",
        "last_name": "Raza",
        "phone": "0311-1234567",
        "role": "cashier",
        "password": "StrongPass123!",
        "confirm_password": "StrongPass123!",
    }
    r = req("POST", "/api/company-users/", token=state["OWNER_TOKEN"], json_body=body, label="Create Cashier")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        if data.get("id"):
            state["CASHIER_ID"] = data["id"]
        elif r.status_code == 400:
            lr = req("GET", "/api/company-users/", token=state["OWNER_TOKEN"],
                      label="(fallback) look up existing cashier")
            if lr is not None and lr.status_code == 200:
                items = jbody(lr).get("results", [])
                match = next((u for u in items if u.get("email") == "cashier1@abcstore.pk"), None)
                if match:
                    state["CASHIER_ID"] = match["id"]
                    print(f"  {C.YELLOW}↳ Using existing cashier id={state['CASHIER_ID']}{C.END}")

    r = req("GET", "/api/company-users/", token=state["OWNER_TOKEN"], label="List Company Users")
    if r is not None:
        check("status 200", r.status_code == 200)

    cid = state["CASHIER_ID"]
    r = req("GET", f"/api/user-permissions/{cid}/panel/", token=state["OWNER_TOKEN"], label="Get Permission Panel")
    if r is not None:
        check("status 200", r.status_code == 200)

    r = req("POST", f"/api/user-permissions/{cid}/assign/", token=state["OWNER_TOKEN"],
            json_body={"permission_ids": [1, 2, 3, 4]}, label="Assign Permissions")
    if r is not None:
        check("status 200", r.status_code == 200)


# ============================================================
# 04 — Subscription Management
# ============================================================
def step_subscription_management():
    section("Subscription Management")
    if not state["ADMIN_TOKEN"]:
        return skip("no admin token")

    body = {
        "name": "Starter",
        "description": "Perfect for small retailers",
        "is_trial": False,
        "price_per_month": 2000,
        "duration_days": 30,
        "max_products": 200,
        "max_users": 5,
        "max_customers": 500,
        "max_sales_per_month": 0,
        "max_categories": 20,
        "includes_fbr_di": True,
        "includes_inventory": True,
        "includes_returns": True,
        "includes_debit_credit_notes": True,
        "includes_basic_reports": True,
    }
    r = req("POST", "/api/subscription-plans/", token=state["ADMIN_TOKEN"], json_body=body,
            label="Create Subscription Plan")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        if data.get("id"):
            state["PLAN_ID"] = data["id"]

    r = req("POST", "/api/subscriptions/assign/", token=state["ADMIN_TOKEN"],
            json_body={"company_id": state["COMPANY_ID"], "plan_id": state["PLAN_ID"],
                       "notes": "First subscription for ABC Store"},
            label="Assign Plan to Company")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        if data.get("id"):
            state["SUBSCRIPTION_ID"] = data["id"]

    if state["OWNER_TOKEN"]:
        r = req("GET", "/api/subscriptions/my-status/", token=state["OWNER_TOKEN"],
                label="Check My Subscription Status")
        if r is not None:
            check("status 200", r.status_code == 200)
            check("has usage data", "usage" in jbody(r))
    else:
        skip("no owner token — skipping subscription status check")

    r = req("POST", f"/api/subscriptions/{state['SUBSCRIPTION_ID']}/extend/", token=state["ADMIN_TOKEN"],
            json_body={"days": 7, "notes": "Goodwill extension for new client"}, label="Extend Subscription")
    if r is not None:
        check("status 200", r.status_code == 200)


# ============================================================
# 05 — Products & Categories
# ============================================================
def step_products_categories():
    section("Products & Categories")
    if not state["OWNER_TOKEN"]:
        return skip("no owner token")

    r = req("POST", "/api/categories/", token=state["OWNER_TOKEN"],
            json_body={"name": "Beverages", "description": "Cold drinks, water, juices"},
            label="Create Category")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        if data.get("id"):
            state["CATEGORY_ID"] = data["id"]
        elif r.status_code == 400:
            lr = req("GET", "/api/categories/", token=state["OWNER_TOKEN"],
                      label="(fallback) look up existing category")
            if lr is not None and lr.status_code == 200:
                items = jbody(lr)
                items = items.get("results", items) if isinstance(items, dict) else items
                match = next((c for c in items if c.get("name") == "Beverages"), None)
                if match:
                    state["CATEGORY_ID"] = match["id"]
                    print(f"  {C.YELLOW}↳ Using existing category id={state['CATEGORY_ID']}{C.END}")

    body = {
        "name": "Pepsi 500ml",
        "category": state["CATEGORY_ID"],
        "selling_price": "80.00",
        "cost_price": "60.00",
        "barcode": "8901234567890",
        "sku": "PEP-500",
        "unit_of_measure": "Numbers, pieces, units",
        "hs_code": "",
        "fbr_sale_type": "Goods at standard rate (default)",
        "tax_rate_percent": "18%",
        "track_inventory": True,
        "current_stock": 100,
        "low_stock_threshold": 10,
    }
    r = req("POST", "/api/products/", token=state["OWNER_TOKEN"], json_body=body, label="Create Product")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        if data.get("id"):
            state["PRODUCT_ID"] = data["id"]
        elif r.status_code == 400:
            lr = req("GET", "/api/products/barcode/8901234567890/", token=state["OWNER_TOKEN"],
                      label="(fallback) look up existing product by barcode")
            if lr is not None and lr.status_code == 200 and jbody(lr).get("id"):
                state["PRODUCT_ID"] = jbody(lr)["id"]
                print(f"  {C.YELLOW}↳ Using existing product id={state['PRODUCT_ID']}{C.END}")

    r = req("GET", "/api/products/search/", token=state["OWNER_TOKEN"], params={"q": "pepsi"},
            label="Search Products")
    if r is not None:
        check("status 200", r.status_code == 200)
        check("response is a list", isinstance(jbody(r), list))

    r = req("GET", "/api/products/barcode/8901234567890/", token=state["OWNER_TOKEN"],
            label="Get Product by Barcode")
    if r is not None:
        check("status 200", r.status_code == 200)

    r = req("PATCH", f"/api/products/{state['PRODUCT_ID']}/stock/", token=state["OWNER_TOKEN"],
            json_body={"adjustment": 50, "reason": "Stock received from supplier"}, label="Adjust Stock")
    if r is not None:
        check("status 200", r.status_code == 200)


# ============================================================
# 06 — Customers
# ============================================================
def step_customers():
    section("Customers")
    if not state["OWNER_TOKEN"]:
        return skip("no owner token")

    r = req("GET", "/api/customers/walkin/", token=state["OWNER_TOKEN"], label="Get Walk-In Customer")
    if r is not None:
        check("status 200", r.status_code == 200)
        data = jbody(r)
        check("is_walk_in is true", data.get("is_walk_in") is True)
        if data.get("id"):
            state["CUSTOMER_ID"] = data["id"]

    body = {
        "name": "XYZ Company",
        "ntn_cnic": "1234567",
        "registration_type": "Registered",
        "province": "Punjab",
        "address": "456 Business Ave, Lahore",
        "phone": "042-1234567",
        "email": "xyz@company.pk",
    }
    r = req("POST", "/api/customers/", token=state["OWNER_TOKEN"], json_body=body,
            label="Create Registered Customer")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        if data.get("id"):
            state["REGISTERED_CUSTOMER_ID"] = data["id"]
        elif r.status_code == 400:
            lr = req("GET", "/api/customers/search/", token=state["OWNER_TOKEN"], params={"q": "xyz"},
                      label="(fallback) look up existing customer")
            if lr is not None and lr.status_code == 200:
                items = jbody(lr)
                if isinstance(items, list) and items:
                    state["REGISTERED_CUSTOMER_ID"] = items[0]["id"]
                    print(f"  {C.YELLOW}↳ Using existing customer id={state['REGISTERED_CUSTOMER_ID']}{C.END}")

    r = req("GET", "/api/customers/search/", token=state["OWNER_TOKEN"], params={"q": "xyz"},
            label="Search Customers")
    if r is not None:
        check("status 200", r.status_code == 200)


# ============================================================
# 07 — Complete POS Sale Flow
# ============================================================
def step_pos_sale_flow():
    section("Complete POS Sale Flow")
    if not state["OWNER_TOKEN"]:
        return skip("no owner token")

    r = req("POST", "/api/cash-sessions/open/", token=state["OWNER_TOKEN"],
            json_body={"opening_balance": "5000.00", "opening_note": "Morning shift start"},
            label="Step 1 — Open Cash Session")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        check("status is open", data.get("status") == "open")
        if data.get("id"):
            state["CASH_SESSION_ID"] = data["id"]

    r = req("POST", "/api/sales/", token=state["OWNER_TOKEN"],
            json_body={"customer": state["CUSTOMER_ID"], "sale_type": "Sale Invoice", "notes": ""},
            label="Step 2 — Create Draft Sale")
    if r is not None:
        check("status 201", r.status_code == 201)
        data = jbody(r)
        check("status is draft", data.get("status") == "draft")
        if data.get("id"):
            state["SALE_ID"] = data["id"]

    r = req("POST", f"/api/sales/{state['SALE_ID']}/add-line/", token=state["OWNER_TOKEN"],
            json_body={"product_id": state["PRODUCT_ID"], "quantity": "2", "discount_amount": "0"},
            label="Step 3 — Add Product Line")
    if r is not None:
        check("status 200", r.status_code == 200)
        lines = jbody(r).get("lines", [])
        check("has at least one line", len(lines) > 0)
        if lines and lines[0].get("id"):
            state["ORIGINAL_LINE_ID"] = lines[0]["id"]

    r = req("POST", f"/api/sales/{state['SALE_ID']}/add-payment/", token=state["OWNER_TOKEN"],
            json_body={"payment_method": "cash", "amount": "200.00"}, label="Step 4 — Add Payment")
    if r is not None:
        check("status 200", r.status_code == 200)
        check("has at least one payment", len(jbody(r).get("payments", [])) > 0)

    r = req("POST", f"/api/sales/{state['SALE_ID']}/complete/", token=state["OWNER_TOKEN"],
            json_body={}, label="Step 5 — Complete Sale")
    if r is not None:
        check("status 200", r.status_code == 200)
        data = jbody(r)
        check("status is completed", data.get("status") == "completed")
        check("fbr_submission_status is pending", data.get("fbr_submission_status") == "pending")

    r = req("GET", f"/api/sales/{state['SALE_ID']}/detail/", token=state["OWNER_TOKEN"],
            label="Step 6 — Get Sale Detail")
    if r is not None:
        check("status 200", r.status_code == 200)
        check("has fbr_invoice_number field", "fbr_invoice_number" in jbody(r))

    r = req("GET", f"/api/receipts/{state['SALE_ID']}/thermal/", token=state["OWNER_TOKEN"],
            label="Step 7 — Get Thermal Receipt")
    if r is not None:
        check("status 200", r.status_code == 200)
        check("has url field", "url" in jbody(r))

    r = req("GET", f"/api/receipts/{state['SALE_ID']}/a4/", token=state["OWNER_TOKEN"],
            label="Step 8 — Get A4 Invoice")
    if r is not None:
        check("status 200", r.status_code == 200)

    r = req("POST", f"/api/cash-sessions/{state['CASH_SESSION_ID']}/close/", token=state["OWNER_TOKEN"],
            json_body={"closing_balance": "5160.00", "closing_note": "End of morning shift"},
            label="Step 9 — Close Cash Session")
    if r is not None:
        check("status 200", r.status_code == 200)
        check("status is closed", jbody(r).get("status") == "closed")


# ============================================================
# 08 — Returns & Debit Notes
# ============================================================
def step_returns_debit_notes():
    section("Returns & Debit Notes")
    if not state["OWNER_TOKEN"]:
        return skip("no owner token")

    body = {
        "original_sale_id": state["SALE_ID"],
        "reason": "defective",
        "reason_notes": "Product was damaged",
        "lines": [{"original_line_id": state["ORIGINAL_LINE_ID"], "quantity_returned": 2}],
    }
    r = req("POST", "/api/returns/", token=state["OWNER_TOKEN"], json_body=body, label="Create Return (Full)")
    if r is not None:
        check("status 201", r.status_code == 201)
        check("status is completed", jbody(r).get("status") == "completed")

    body = {
        "original_sale_id": state["SALE_ID"],
        "reason": "forgotten_items",
        "reason_notes": "Forgot to add delivery charge",
        "payment_method": "cash",
        "amount_paid": "200.00",
        "lines": [{
            "description": "Delivery Charge",
            "quantity": 1,
            "unit_price": "150.00",
            "tax_rate_percent": "0%",
            "fbr_sale_type": "Services",
        }],
    }
    r = req("POST", "/api/debit-notes/", token=state["OWNER_TOKEN"], json_body=body, label="Create Debit Note")
    if r is not None:
        check("status 200/201", r.status_code in (200, 201))


# ============================================================
# 09 — Reports
# ============================================================
def step_reports():
    section("Reports")
    if state["OWNER_TOKEN"]:
        r = req("GET", "/api/reports/sales/today/", token=state["OWNER_TOKEN"], label="Today Sales Summary")
        if r is not None:
            check("status 200", r.status_code == 200)
            data = jbody(r)
            check("has total_sales", "total_sales" in data)
            check("has hourly_breakdown", "hourly_breakdown" in data)

        r = req("GET", "/api/reports/sales/", token=state["OWNER_TOKEN"],
                params={"from": "2026-01-01", "to": "2026-12-31"}, label="Sales Date Range Report")
        if r is not None:
            check("status 200", r.status_code == 200)

        r = req("GET", "/api/reports/products/top/", token=state["OWNER_TOKEN"], params={"limit": 10},
                label="Top Products")
        if r is not None:
            check("status 200", r.status_code == 200)

        r = req("GET", "/api/reports/inventory/", token=state["OWNER_TOKEN"], label="Inventory Report")
        if r is not None:
            check("status 200", r.status_code == 200)

        r = req("GET", "/api/reports/inventory/", token=state["OWNER_TOKEN"],
                params={"low_stock_only": "true"}, label="Low Stock Only")
        if r is not None:
            check("status 200", r.status_code == 200)
    else:
        skip("owner reports — no owner token")

    if state["ADMIN_TOKEN"]:
        r = req("GET", "/api/reports/admin/invoices/", token=state["ADMIN_TOKEN"], label="Admin — All Invoices")
        if r is not None:
            check("status 200", r.status_code == 200)
            check("has platform_summary", "platform_summary" in jbody(r))

        r = req("GET", "/api/reports/admin/activity/", token=state["ADMIN_TOKEN"], label="Admin — User Activity")
        if r is not None:
            check("status 200", r.status_code == 200)
    else:
        skip("admin reports — no admin token")


# ============================================================
# 10 — FBR Sandbox
# ============================================================
def step_fbr_sandbox():
    section("FBR Sandbox")
    if not state["ADMIN_TOKEN"]:
        return skip("no admin token")

    r = req("POST", f"/api/fbr/companies/{state['COMPANY_ID']}/clear-scenarios/", token=state["ADMIN_TOKEN"],
            json_body={}, label="Clear All Scenarios")
    if r is None:
        return
    check("status 200", r.status_code == 200)
    data = jbody(r)
    check("has task_id", "task_id" in data)
    task_id = data.get("task_id")
    if not task_id:
        return

    print(f"  {C.YELLOW}Polling task status (async Celery task)...{C.END}")
    for attempt in range(10):
        time.sleep(2)
        r = req("GET", f"/api/fbr/task-status/{task_id}/", token=state["ADMIN_TOKEN"],
                 label=f"Check Task Status (attempt {attempt + 1})")
        if r is None:
            break
        check("status 200", r.status_code == 200)
        task_status = jbody(r).get("status")
        print(f"    task status: {task_status}")
        if task_status in ("SUCCESS", "FAILURE"):
            break


# ============================================================
# Token lifecycle — runs LAST since logout invalidates the admin token
# ============================================================
def step_token_lifecycle():
    section("Token Refresh & Logout (Admin) — runs last on purpose")
    if state.get("ADMIN_REFRESH"):
        r = req("POST", "/api/auth/refresh/", json_body={"refresh": state["ADMIN_REFRESH"]},
                label="Refresh Admin Token")
        if r is not None:
            check("status 200", r.status_code == 200)
            data = jbody(r)
            # Some setups rotate + blacklist the refresh token on every use.
            # If a new one comes back, switch to it so Logout below isn't
            # handed an already-blacklisted token.
            if data.get("refresh"):
                state["ADMIN_REFRESH"] = data["refresh"]
            if data.get("access"):
                state["ADMIN_TOKEN"] = data["access"]
    else:
        skip("no refresh token captured during login")

    if state["ADMIN_TOKEN"] and state.get("ADMIN_REFRESH"):
        r = req("POST", "/api/auth/logout/", token=state["ADMIN_TOKEN"],
                json_body={"refresh": state["ADMIN_REFRESH"]}, label="Logout Admin")
        if r is not None:
            check("status 200/204", r.status_code in (200, 204))
    else:
        skip("missing admin token/refresh")


# ============================================================
# Main
# ============================================================
def main():
    print(f"{C.BOLD}FBR POS Platform — API Test Runner{C.END}")
    print(f"Target: {BASE_URL}")

    step_login_admin()
    step_admin_profile()
    step_company_management()
    step_create_owner()
    step_login_owner()
    step_user_management_rest()
    step_subscription_management()
    step_products_categories()
    step_customers()
    step_pos_sale_flow()
    step_returns_debit_notes()
    step_reports()
    step_fbr_sandbox()
    step_token_lifecycle()

    print(f"\n{C.BOLD}=== SUMMARY ==={C.END}")
    total = PASS + FAIL
    print(f"  {C.GREEN}Passed: {PASS}{C.END} / {total}")
    print(f"  {C.RED}Failed: {FAIL}{C.END} / {total}")
    if FAILED_TESTS:
        print("\n  Failed checks:")
        for f in FAILED_TESTS:
            print(f"   - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()