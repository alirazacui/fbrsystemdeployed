"""
========================================================
digital_invoicing/invoice_builder.py
 
FBR Invoice JSON Builder
 
Assembles the complete FBR-format invoice JSON from a Sale object.
This is the bridge between our Django models and the FBR API payload.
 
FBR invoice JSON structure (PRAL DI API v1.3):
{
    "invoiceType":             "Sale Invoice",
    "invoiceDate":             "2025-01-15T10:30:00",
    "sellerBusinessName":      "ABC Store",
    "sellerNTNCNIC":           "7000007",
    "sellerProvince":          "Punjab",
    "sellerAddress":           "123 Main St, Lahore",
    "buyerBusinessName":       "XYZ Company",
    "buyerNTNCNIC":            "1234567",
    "buyerRegistrationType":   "Registered",
    "buyerProvince":           "Punjab",
    "buyerAddress":            "456 Other St, Karachi",
    "invoiceRefNo":            "",  (for debit/credit notes only)
    "scenarioId":              "SN002",
    "items": [
        {
            "hsCode":                          "0101.2100",
            "productDescription":              "Widget A",
            "rate":                            "18%",
            "uoM":                             "Numbers, pieces, units",
            "quantity":                        2.0,
            "valueSalesExcludingST":           200.00,
            "fixedNotifiedValueOrRetailPrice": 0,
            "salesTaxApplicable":              36.00,
            "salesTaxWithheldAtSource":        0,
            "extraTax":                        "",
            "furtherTax":                      0,
            "sroScheduleNo":                   "",
            "sroItemSerialNo":                 "",
            "fedPayable":                      0,
            "discount":                        0,
            "totalValues":                     236.00,
            "saleType":                        "Goods at standard rate (default)"
        }
    ]
}
========================================================
"""
 
 
class FBRInvoiceBuilder:
    """
    Builds the complete FBR invoice JSON payload from a Sale instance.
 
    Usage:
        builder = FBRInvoiceBuilder(sale)
        payload = builder.build()
        # payload is ready to POST to FBR
    """
 
    def __init__(self, sale):
        self.sale    = sale
        self.company = sale.company
        self.customer = sale.customer
 
    def build(self) -> dict:
        """
        Assembles and returns the complete FBR invoice JSON dict.
        """
        payload = {
            # ── Invoice header ──────────────────────────────────────
            "invoiceType": self.sale.sale_type,
            "invoiceDate": self._format_date(self.sale.completed_at),
 
            # ── Seller (our client company) ─────────────────────────
            "sellerBusinessName": self.company.business_name,
            "sellerNTNCNIC":      self.company.ntn,
            "sellerProvince":     self._extract_province(self.company.address),
            "sellerAddress":      self.company.address,
 
            # ── Buyer (customer) ────────────────────────────────────
            **self.customer.get_fbr_buyer_payload(),
 
            # ── Reference (for debit/credit notes) ──────────────────
            "invoiceRefNo": (
                self.sale.original_sale.fbr_invoice_number
                if self.sale.original_sale else ""
            ),
 
            # ── Scenario ────────────────────────────────────────────
            "scenarioId": self._determine_scenario(),
 
            # ── Line items ──────────────────────────────────────────
            "items": self._build_items(),
        }
        return payload
 
    def _format_date(self, dt) -> str:
        """Format datetime to FBR expected format: YYYY-MM-DD"""
        if dt is None:
            from django.utils import timezone
            dt = timezone.now()
        return dt.strftime("%Y-%m-%d")
 
    def _extract_province(self, address: str) -> str:
        """
        Try to extract province from address string.
        Falls back to 'Punjab' if not determinable.
        FBR requires a valid province value.
        """
        address_lower = address.lower()
        province_map  = {
            "punjab":              "Punjab",
            "lahore":              "Punjab",
            "faisalabad":          "Punjab",
            "multan":              "Punjab",
            "sindh":               "Sindh",
            "karachi":             "Sindh",
            "hyderabad":           "Sindh",
            "kpk":                 "Khyber Pakhtunkhwa",
            "khyber pakhtunkhwa":  "Khyber Pakhtunkhwa",
            "peshawar":            "Khyber Pakhtunkhwa",
            "balochistan":         "Balochistan",
            "quetta":              "Balochistan",
            "islamabad":           "Islamabad",
            "gilgit":              "Gilgit-Baltistan",
            "azad kashmir":        "Azad Jammu & Kashmir",
            "ajk":                 "Azad Jammu & Kashmir",
        }
        for keyword, province in province_map.items():
            if keyword in address_lower:
                return province
        return "Punjab"   # safe default
 
    def _determine_scenario(self) -> str:
        """
        Determines the FBR scenario ID for this sale.
 
        Logic (simplified — covers the most common cases):
        - Registered buyer  + standard rate goods  → SN001
        - Unregistered buyer + standard rate goods → SN002
        - Registered buyer  + reduced rate goods   → SN005
        - Exempted goods                           → SN006
        - Zero rated goods                         → SN007
        - Third schedule goods                     → SN008
        - Standard rate to end consumer (retailer) → SN026
        - Third schedule to end consumer           → SN027
        - Reduced rate to end consumer             → SN028
 
        If multiple sale types exist in one invoice, use the first line's type.
        """
        from pos.models import BuyerRegistrationType
 
        is_registered = (
            self.customer.registration_type == BuyerRegistrationType.REGISTERED
        )
 
        # Get unique sale types from lines
        sale_types = list(
            self.sale.lines.values_list("fbr_sale_type", flat=True).distinct()
        )
        first_type = sale_types[0] if sale_types else "Goods at standard rate (default)"
 
        scenario_map = {
            # Registered buyer scenarios
            ("Goods at standard rate (default)", True):        "SN001",
            ("Goods at Reduced Rate",             True):        "SN005",
            # Unregistered buyer / end consumer scenarios
            ("Goods at standard rate (default)", False):        "SN002",
            ("Goods at Reduced Rate",             False):        "SN028",
            ("3rd Schedule Goods",                False):        "SN027",
            # Goods-type scenarios (registration type doesn't matter)
        }
 
        # Special cases regardless of buyer type
        special = {
            "Exempt Goods":                  "SN006",
            "Goods at zero-rate":            "SN007",
            "3rd Schedule Goods":            "SN008",
            "Steel Melting and re-rolling":  "SN003",
            "Ship breaking":                 "SN004",
            "Cotton Ginners":                "SN009",
            "Telecommunication services":    "SN010",
            "Toll Manufacturing":            "SN011",
            "Petroleum Products":            "SN012",
            "Electricity Supply to Retailers": "SN013",
            "Gas to CNG stations":           "SN014",
            "Mobile Phones":                 "SN015",
            "Processing/ Conversion of Goods": "SN016",
            "Goods (FED in ST Mode)":        "SN017",
            "Services (FED in ST Mode)":     "SN018",
            "Services":                      "SN019",
            "Electric Vehicle":              "SN020",
            "Cement /Concrete Block":        "SN021",
            "Potassium Chlorate":            "SN022",
            "CNG Sales":                     "SN023",
            "Goods as per SRO.297(|)/2023":  "SN025",
        }
 
        if first_type in special:
            return special[first_type]
 
        # Use registration-type-dependent mapping
        key = (first_type, is_registered)
        return scenario_map.get(key, "SN002")   # default to SN002 (unregistered standard)
 
    def _build_items(self) -> list:
        """Build the items array from all SaleLines."""
        return [
            line.get_fbr_item_payload()
            for line in self.sale.lines.all()
        ]
