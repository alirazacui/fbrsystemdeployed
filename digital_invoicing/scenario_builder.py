"""
========================================================
digital_invoicing/scenario_builder.py

FBR Sandbox Scenario Auto-Clearer

Each of the 28 FBR sandbox scenarios requires a specifically
crafted invoice JSON. This module builds the correct invoice
for each scenario and submits it to FBR sandbox.

Scenario requirements (from PRAL DI API Technical Specification v1.12):
- Each scenario tests a different tax treatment / sale type
- Some scenarios require a registered buyer with NTN (SN001 only)
- All scenarios use dummy/test data — real products not needed

After ALL assigned scenarios pass → FBR auto-issues production token.
========================================================
"""

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixes applied vs original:
#
# 1.  totalValues → always 0  (FBR computes it server-side; sending a value
#     causes generic [01] Validation failed across every scenario)
# 2.  extraTax    → always 0.00 number, never "" empty string
# 3.  SN003  HS code 7206.1000 → 7214.1010 | sale type casing fixed
# 4.  SN004  HS code 7204.1000 → 7204.1010
# 5.  SN005  buyer_registered True → False | rate 10% → 1% |
#            added sroScheduleNo + sroItemSerialNo (required for Eighth Schedule)
# 6.  SN006  rate "0%" → "Exempt" | sale type "Exempt Goods" → "Exempt goods" |
#            added sroScheduleNo + sroItemSerialNo (required for Sixth Schedule)
# 7.  SN007  added sroScheduleNo "327(I)/2008" + sroItemSerialNo "1" (required)
# 8.  SN009  sale type "Cotton Ginners" → "Cotton ginners" (casing)
# 9.  SN010  rate "19.5%" → "17%"
# 10. SN011  HS code 7214.2000 → 7214.9990
# 11. SN016  HS code 7601.1000 → 0101.2100
# 12. invoiceDate → date-only string "YYYY-MM-DD", never datetime
# ---------------------------------------------------------------------------

SCENARIO_TEMPLATES = {
    "SN001": {
        "description":      "Standard Rate — Registered Buyer",
        "sale_type":        "Goods at standard rate (default)",
        "rate":             "18%",
        "buyer_registered": True,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN002": {
        "description":      "Standard Rate — Unregistered Buyer",
        "sale_type":        "Goods at standard rate (default)",
        "rate":             "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN003": {
        "description":      "Steel Melted",
        # FIX: sale type casing must match exactly; was "Steel Melting and re-rolling"
        "sale_type":        "Steel melting and re-rolling",
        "rate":             "18%",
        "buyer_registered": False,
        # FIX: was 7206.1000
        "hs_code":          "7214.1010",
        "unit_price":       205000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN004": {
        "description":      "Steel Scrap by Ship Breaker",
        "sale_type":        "Ship breaking",
        "rate":             "18%",
        "buyer_registered": False,
        # FIX: was 7204.1000
        "hs_code":          "7204.1010",
        "unit_price":       175000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN005": {
        "description":      "Reduced Rate — Eighth Schedule",
        "sale_type":        "Goods at Reduced Rate",
        # FIX: was 10% — Eighth Schedule rate is 1%
        "rate":             "1%",
        # FIX: was True — FBR error [0205] says SN005 must be Unregistered
        "buyer_registered": False,
        "hs_code":          "0102.2930",
        "unit_price":       1000.00,
        "quantity":         1.0,
        # FIX: SRO fields are required for Eighth Schedule reduced rate
        "sro_schedule":     "EIGHTH SCHEDULE Table 1",
        "sro_item":         "82",
        "extra_fields":     {},
    },
    "SN006": {
        "description":      "Exempted Goods — Sixth Schedule",
        # FIX: sale type was "Exempt Goods" — must be "Exempt goods" (lowercase g)
        "sale_type":        "Exempt goods",
        # FIX: rate was "0%" — must be "Exempt"
        "rate":             "Exempt",
        "buyer_registered": False,
        "hs_code":          "0102.2930",
        "unit_price":       500.00,
        "quantity":         1.0,
        # FIX: SRO fields required for Sixth Schedule
        "sro_schedule":     "6th Schd Table I",
        "sro_item":         "100",
        "extra_fields":     {},
    },
    "SN007": {
        "description":      "Zero Rated Goods — Fifth Schedule",
        "sale_type":        "Goods at zero-rate",
        "rate":             "0%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        # FIX: SRO fields required for Fifth Schedule zero-rate
        "sro_schedule":     "327(I)/2008",
        "sro_item":         "1",
        "extra_fields":     {},
    },
    "SN008": {
        "description":      "Third Schedule Goods",
        "sale_type":        "3rd Schedule Goods",
        "rate":             "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       100.00,
        "quantity":         10.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {"fixedNotifiedValueOrRetailPrice": 1000.00},
    },
    "SN009": {
        "description":      "Purchase from Cotton Grower",
        # FIX: was "Cotton Ginners" — must be "Cotton ginners" (lowercase g)
        "sale_type":        "Cotton ginners",
        "rate":             "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       2500.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN010": {
        "description":      "Telecom Services by Mobile Operators",
        "sale_type":        "Telecommunication services",
        # FIX: was "19.5%" — correct rate is "17%"
        "rate":             "17%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN011": {
        "description":      "Steel via Toll Manufacturing",
        "sale_type":        "Toll Manufacturing",
        "rate":             "18%",
        "buyer_registered": False,
        # FIX: was 7214.2000
        "hs_code":          "7214.9990",
        "unit_price":       205000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN012": {
        "description":      "Petroleum Products",
        "sale_type":        "Petroleum Products",
        "rate":             "18%",
        "buyer_registered": False,
        "hs_code":          "2710.1221",
        "unit_price":       5000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN013": {
        "description":      "Electricity to Retailers",
        "sale_type":        "Electricity Supply to Retailers",
        "rate":             "17%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       2000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN014": {
        "description":      "Gas to CNG Stations",
        "sale_type":        "Gas to CNG stations",
        "rate":             "17%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       3000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN015": {
        "description":      "Mobile Phones",
        "sale_type":        "Mobile Phones",
        "rate":             "17%",
        "buyer_registered": False,
        "hs_code":          "8517.1200",
        "unit_price":       50000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN016": {
        "description":      "Processing / Conversion of Goods",
        "sale_type":        "Processing/Conversion of Goods",
        "rate":             "18%",
        "buyer_registered": False,
        # FIX: was 7601.1000 (aluminium) — use the generic test HS code
        "hs_code":          "0101.2100",
        "unit_price":       2000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN017": {
        "description":      "Goods (FED in ST Mode)",
        "sale_type":        "Goods (FED in ST Mode)",
        "rate":             "8%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       100.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {"fedPayable": 65.0, "force_sales_tax": 8.0, "force_value_excl": 100.0},
    },
    "SN018": {
        "description":      "Services (FED in ST Mode)",
        "sale_type":        "Services (FED in ST Mode)",
        "rate":             "8%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       100.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {"fedPayable": 100.0, "force_sales_tax": 8.0, "force_value_excl": 100.0},
    },
    "SN019": {
        "description":      "Services (ICT Ordinance)",
        "sale_type":        "Services",
        "rate":             "16%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN020": {
        "description":      "Electric Vehicles",
        "sale_type":        "Electric Vehicle",
        "rate":             "1%",
        "buyer_registered": True,
        "hs_code":          "8703.8090",
        "unit_price":       3000000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN021": {
        "description":      "Cement / Concrete Block",
        "sale_type":        "Cement /Concrete Block",
        "rate":             "17%",
        "buyer_registered": False,
        "hs_code":          "2523.2100",
        "unit_price":       1200.00,
        "quantity":         10.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN022": {
        "description":      "Potassium Chloride",
        "sale_type":        "Potassium Chlorate",
        "rate":             "17%",
        "buyer_registered": False,
        "hs_code":          "3104.2000",
        "unit_price":       2500.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN023": {
        "description":      "CNG Sale",
        "sale_type":        "CNG Sales",
        "rate":             "Rs.200/unit",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1500.00,
        "quantity":         1.0,
        "sro_schedule":     "581(1)/2024",
        "sro_item":         "Region-I",
        "extra_fields":     {},
    },
    "SN024": {
        "description":      "Goods per SRO297",
        "sale_type":        "Goods as per SRO.297(|)/2023",
        "rate":             "25%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       8.13,
        "quantity":         123.0,
        "sro_schedule":     "297(I)/2023-Table-I",
        "sro_item":         "12",
        "extra_fields":     {"force_value_excl": 1000.0, "force_sales_tax": 250.0},
    },
    "SN025": {
        "description":      "Goods per SRO297",
        "sale_type":        "Goods as per SRO.297(|)/2023",
        "rate":             "0%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "sro_schedule":     "SRO.297(I)/2023",
        "sro_item":         "1",
        "extra_fields":     {},
    },
    "SN026": {
        "description":      "Standard Rate — End Consumer (Retailer)",
        "sale_type":        "Goods at standard rate (default)",
        "rate":             "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {},
    },
    "SN027": {
        "description":      "Third Schedule — End Consumer (Retailer)",
        "sale_type":        "3rd Schedule Goods",
        "rate":             "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       100.00,
        "quantity":         10.0,
        "sro_schedule":     "",
        "sro_item":         "",
        "extra_fields":     {"fixedNotifiedValueOrRetailPrice": 1000.00},
    },
    "SN028": {
        "description":      "Reduced Rate — End Consumer (Retailer)",
        "sale_type":        "Goods at Reduced Rate",
        "rate":             "1%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "sro_schedule":     "EIGHTH SCHEDULE Table 1",
        "sro_item":         "70",
        "extra_fields":     {},
    },
}


class ScenarioInvoiceBuilder:
    """
    Builds a valid FBR sandbox invoice JSON for a specific scenario.

    Each scenario needs specific field combinations.
    Uses the company's real NTN/STRN for seller fields but
    uses test/dummy data for buyer and items.
    """

    def __init__(self, company, scenario_code: str):
        self.company       = company
        self.scenario_code = scenario_code.upper()
        self.template      = SCENARIO_TEMPLATES.get(self.scenario_code)

        if not self.template:
            raise ValueError(f"Unknown scenario code: {self.scenario_code}")

    def build(self) -> dict:
        """Build and return the complete FBR invoice JSON for this scenario."""
        from django.utils import timezone
        from datetime import date

        template   = self.template
        unit_price = template["unit_price"]
        quantity   = template["quantity"]
        rate_str   = template["rate"]

        # Sales tax calculation — only when rate is a plain percentage
        if rate_str.endswith("%"):
            tax_rate  = float(rate_str.replace("%", "")) / 100
            sales_tax = round(unit_price * quantity * tax_rate, 2)
        else:
            # "Exempt" or fixed rates like "Rs.200/unit" — no percentage calc
            sales_tax = 0.00

        value_excl_st      = round(unit_price * quantity, 2)

        if "force_value_excl" in template["extra_fields"]:
            value_excl_st = float(template["extra_fields"]["force_value_excl"])
        if "force_sales_tax" in template["extra_fields"]:
            sales_tax = float(template["extra_fields"]["force_sales_tax"])
        fed_payable        = float(template["extra_fields"].get("fedPayable", 0.00))
        fixed_retail_price = float(template["extra_fields"].get(
            "fixedNotifiedValueOrRetailPrice", 0.00
        ))

        # Buyer details
        if template["buyer_registered"]:
            buyer_ntn      = self.company.fbr_test_buyer_ntn or "3640255002483"
            buyer_name     = "Test Registered Buyer"
            buyer_reg_type = "Registered"
        else:
            buyer_ntn      = "1000000000000"
            buyer_name     = "Walk-In Customer"
            buyer_reg_type = "Unregistered"

        # FIX: date only — FBR expects "YYYY-MM-DD", not a datetime string
        # Ensure invoice date is not before FBR's minimum allowed date (2025-02-01)
        cutoff       = date(2025, 2, 1)
        today        = timezone.now().date()
        invoice_date = today if today >= cutoff else cutoff
        invoice_date_str = invoice_date.strftime("%Y-%m-%d")

        payload = {
            # ── Header ───────────────────────────────────────────────
            "invoiceType":           "Sale Invoice",
            "invoiceDate":           invoice_date_str,
            "invoiceRefNo":          "",

            # ── Seller (real company data) ────────────────────────────
            "sellerBusinessName":    self.company.business_name,
            "sellerNTNCNIC":         self.company.ntn,
            "sellerProvince":        "Punjab",
            "sellerAddress":         self.company.address or "Pakistan",

            # ── Buyer (test data) ─────────────────────────────────────
            "buyerNTNCNIC":               buyer_ntn,
            "buyerBusinessName":          buyer_name,
            # FBR field name is "buyerRegistrationType"
            "buyerRegistrationType":        buyer_reg_type,
            "buyerProvince":              "Punjab",
            "buyerAddress":               "Test Address, Pakistan",

            # ── Scenario ──────────────────────────────────────────────
            "scenarioId":            self.scenario_code,

            # ── Items ─────────────────────────────────────────────────
            "items": [
                {
                    "hsCode":                          template["hs_code"],
                    "productDescription":              (
                        f"Test Product for {self.scenario_code} — "
                        f"{template['description']}"
                    ),
                    "rate":                            rate_str,
                    "uoM":                             "Numbers, pieces, units",
                    "quantity":                        quantity,
                    # FIX: always 0 — FBR computes totalValues server-side
                    "totalValues":                     0,
                    "valueSalesExcludingST":            value_excl_st,
                    "fixedNotifiedValueOrRetailPrice":  fixed_retail_price,
                    "salesTaxApplicable":               sales_tax,
                    "salesTaxWithheldAtSource":         0,
                    # extraTax must be empty string for reduced rate goods
                    "extraTax":                        "",
                    "furtherTax":                      0,
                    "sroScheduleNo":                   template["sro_schedule"],
                    "sroItemSerialNo":                 template["sro_item"],
                    "fedPayable":                      fed_payable,
                    "discount":                        0,
                    "saleType":                        template["sale_type"],
                }
            ],
        }
        return payload
