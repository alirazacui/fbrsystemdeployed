"""
========================================================
digital_invoicing/scenario_builder.py
 
FBR Sandbox Scenario Auto-Clearer
 
Each of the 28 FBR sandbox scenarios requires a specifically
crafted invoice JSON. This module builds the correct invoice
for each scenario and submits it to FBR sandbox.
 
Scenario requirements (from PRAL DI API Technical Specification v1.3):
- Each scenario tests a different tax treatment / sale type
- Some scenarios require a registered buyer with NTN (SN001, SN005)
- Some require specific sale types (SN003=Steel, SN006=Exempt, etc.)
- All scenarios use dummy/test data — real products not needed
 
After ALL assigned scenarios pass → FBR auto-issues production token.
========================================================
"""
 
import logging
from decimal import Decimal
 
logger = logging.getLogger(__name__)
 
 
# ---------------------------------------------------------------------------
# Scenario invoice templates
#
# Each scenario needs specific fields set correctly.
# Template structure:
#   sale_type           → maps to FBR saleType
#   tax_rate            → maps to FBR rate
#   buyer_registered    → True if scenario needs registered buyer
#   hs_code             → required for some scenarios
#   extra_fields        → any additional item-level overrides
# ---------------------------------------------------------------------------
 
SCENARIO_TEMPLATES = {
    "SN001": {
        "description":      "Standard Rate — Registered Buyer",
        "sale_type":        "Goods at standard rate (default)",
        "tax_rate":         "18%",
        "buyer_registered": True,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN002": {
        "description":      "Standard Rate — Unregistered Buyer",
        "sale_type":        "Goods at standard rate (default)",
        "tax_rate":         "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN003": {
        "description":      "Steel Melted",
        "sale_type":        "Steel Melting and re-rolling",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "7206.1000",
        "unit_price":       5000.00,
        "quantity":         1.0,
        "extra_fields":     {"extraTax": 2.0},
    },
    "SN004": {
        "description":      "Steel Scrap by Ship Breaker",
        "sale_type":        "Ship breaking",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "7204.1000",
        "unit_price":       5000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN005": {
        "description":      "Reduced Rate — Registered Buyer",
        "sale_type":        "Goods at Reduced Rate",
        "tax_rate":         "10%",
        "buyer_registered": True,
        "hs_code":          "0201.1000",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN006": {
        "description":      "Exempted Goods",
        "sale_type":        "Exempt Goods",
        "tax_rate":         "0%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       500.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN007": {
        "description":      "Zero Rated Goods",
        "sale_type":        "Goods at zero-rate",
        "tax_rate":         "0%",
        "buyer_registered": False,
        "hs_code":          "5201.0010",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN008": {
        "description":      "Third Schedule Goods",
        "sale_type":        "3rd Schedule Goods",
        "tax_rate":         "18%",
        "buyer_registered": False,
        "hs_code":          "2402.2010",
        "unit_price":       100.00,
        "quantity":         10.0,
        "extra_fields":     {"fixedNotifiedValueOrRetailPrice": 120.00},
    },
    "SN009": {
        "description":      "Purchase from Cotton Grower",
        "sale_type":        "Cotton Ginners",
        "tax_rate":         "0%",
        "buyer_registered": False,
        "hs_code":          "5201.0010",
        "unit_price":       2000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN010": {
        "description":      "Telecom Services by Mobile Operators",
        "sale_type":        "Telecommunication services",
        "tax_rate":         "19.5%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN011": {
        "description":      "Steel via Toll Manufacturing",
        "sale_type":        "Toll Manufacturing",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "7214.2000",
        "unit_price":       3000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN012": {
        "description":      "Petroleum Products",
        "sale_type":        "Petroleum Products",
        "tax_rate":         "18%",
        "buyer_registered": False,
        "hs_code":          "2710.1221",
        "unit_price":       5000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN013": {
        "description":      "Electricity to Retailers",
        "sale_type":        "Electricity Supply to Retailers",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       2000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN014": {
        "description":      "Gas to CNG Stations",
        "sale_type":        "Gas to CNG stations",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       3000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN015": {
        "description":      "Mobile Phones",
        "sale_type":        "Mobile Phones",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "8517.1200",
        "unit_price":       50000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN016": {
        "description":      "Processing / Conversion of Goods",
        "sale_type":        "Processing/ Conversion of Goods",
        "tax_rate":         "18%",
        "buyer_registered": False,
        "hs_code":          "7601.1000",
        "unit_price":       2000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN017": {
        "description":      "Goods (FED in ST Mode)",
        "sale_type":        "Goods (FED in ST Mode)",
        "tax_rate":         "0%",
        "buyer_registered": False,
        "hs_code":          "2402.2010",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {"fedPayable": 65.0},
    },
    "SN018": {
        "description":      "Services (FED in ST Mode)",
        "sale_type":        "Services (FED in ST Mode)",
        "tax_rate":         "0%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {"fedPayable": 100.0},
    },
    "SN019": {
        "description":      "Services (ICT Ordinance)",
        "sale_type":        "Services",
        "tax_rate":         "15%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN020": {
        "description":      "Electric Vehicles",
        "sale_type":        "Electric Vehicle",
        "tax_rate":         "1%",
        "buyer_registered": True,
        "hs_code":          "8703.8090",
        "unit_price":       3000000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN021": {
        "description":      "Cement / Concrete Block",
        "sale_type":        "Cement /Concrete Block",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "2523.2100",
        "unit_price":       1200.00,
        "quantity":         10.0,
        "extra_fields":     {},
    },
    "SN022": {
        "description":      "Potassium Chloride",
        "sale_type":        "Potassium Chlorate",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "3104.2000",
        "unit_price":       2500.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN023": {
        "description":      "SNNG Sale",
        "sale_type":        "CNG Sales",
        "tax_rate":         "17%",
        "buyer_registered": False,
        "hs_code":          "",
        "unit_price":       1500.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN024": {
        "description":      "Goods per SC004",
        "sale_type":        "Goods at standard rate (default)",
        "tax_rate":         "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {"sroScheduleNo": "SC004", "sroItemSerialNo": "1"},
    },
    "SN025": {
        "description":      "Goods per SRO297",
        "sale_type":        "Goods as per SRO.297(|)/2023",
        "tax_rate":         "0%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {
            "sroScheduleNo":    "SRO.297(I)/2023",
            "sroItemSerialNo":  "1",
        },
    },
    "SN026": {
        "description":      "Standard Rate — End Consumer (Retailer)",
        "sale_type":        "Goods at standard rate (default)",
        "tax_rate":         "18%",
        "buyer_registered": False,
        "hs_code":          "0101.2100",
        "unit_price":       1000.00,
        "quantity":         1.0,
        "extra_fields":     {},
    },
    "SN027": {
        "description":      "Third Schedule — End Consumer (Retailer)",
        "sale_type":        "3rd Schedule Goods",
        "tax_rate":         "18%",
        "buyer_registered": False,
        "hs_code":          "2402.2010",
        "unit_price":       100.00,
        "quantity":         10.0,
        "extra_fields":     {"fixedNotifiedValueOrRetailPrice": 120.00},
    },
    "SN028": {
        "description":      "Reduced Rate — End Consumer (Retailer)",
        "sale_type":        "Goods at Reduced Rate",
        "tax_rate":         "10%",
        "buyer_registered": False,
        "hs_code":          "0201.1000",
        "unit_price":       1000.00,
        "quantity":         1.0,
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
 
        template   = self.template
        unit_price = template["unit_price"]
        quantity   = template["quantity"]
        tax_rate   = float(template["tax_rate"].replace("%", "")) / 100
 
        value_excl_st      = round(unit_price * quantity, 2)
        sales_tax          = round(value_excl_st * tax_rate, 2)
        fed_payable        = float(template["extra_fields"].get("fedPayable", 0))
        extra_tax          = float(template["extra_fields"].get("extraTax", 0))
        fixed_retail_price = float(template["extra_fields"].get(
            "fixedNotifiedValueOrRetailPrice", 0
        ))
        total_values       = round(value_excl_st + sales_tax + fed_payable + extra_tax, 2)
 
        # Buyer details
        if template["buyer_registered"]:
            buyer_ntn            = self.company.fbr_test_buyer_ntn or "0000001"
            buyer_name           = "Test Registered Buyer"
            buyer_reg_type       = "Registered"
        else:
            buyer_ntn            = "1000000000000"
            buyer_name           = "Walk-In Customer"
            buyer_reg_type       = "Unregistered"
 
        payload = {
            # ── Header ───────────────────────────────────────────────
            "invoiceType":           "Sale Invoice",
            "invoiceDate":           timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "invoiceRefNo":          "",
 
            # ── Seller (real company data) ────────────────────────────
            "sellerBusinessName":    self.company.business_name,
            "sellerNTNCNIC":         self.company.ntn,
            "sellerProvince":        "Punjab",
            "sellerAddress":         self.company.address or "Pakistan",
 
            # ── Buyer (test data) ─────────────────────────────────────
            "buyerNTNCNIC":               buyer_ntn,
            "buyerBusinessName":          buyer_name,
            "buyerRegistrationType":      buyer_reg_type,
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
                    "rate":                            template["tax_rate"],
                    "uoM":                             "Numbers, pieces, units",
                    "quantity":                        quantity,
                    "valueSalesExcludingST":            value_excl_st,
                    "fixedNotifiedValueOrRetailPrice":  fixed_retail_price,
                    "salesTaxApplicable":               sales_tax,
                    "salesTaxWithheldAtSource":         0,
                    "extraTax":                        (
                        extra_tax if extra_tax else ""
                    ),
                    "furtherTax":                      0,
                    "sroScheduleNo":                   template["extra_fields"].get(
                        "sroScheduleNo", ""
                    ),
                    "sroItemSerialNo":                 template["extra_fields"].get(
                        "sroItemSerialNo", ""
                    ),
                    "fedPayable":                      fed_payable,
                    "discount":                        0,
                    "totalValues":                     total_values,
                    "saleType":                        template["sale_type"],
                }
            ],
        }
        return payload
 
