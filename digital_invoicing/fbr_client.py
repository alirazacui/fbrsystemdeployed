"""
========================================================
digital_invoicing/fbr_client.py
 
FBR PRAL API Client
Wraps all HTTP calls to PRAL Digital Invoicing endpoints.
 
Sandbox base URL  : https://esp.pral.com.pk/di_data
Production base URL: https://gw.fbr.gov.pk/di_data
 
Endpoints used:
  POST /v1/di/postinvoicedata  → submit invoice
  GET  /v1/di/getinvoice       → verify/fetch submitted invoice
========================================================
"""
 
import logging
import requests
from requests.exceptions import ConnectionError, Timeout, RequestException
 
logger = logging.getLogger(__name__)
 
# ── Base URLs ────────────────────────────────────────────────────────────────
FBR_SANDBOX_BASE    = "https://esp.fbr.gov.pk/di_data"
FBR_PRODUCTION_BASE = "https://gw.fbr.gov.pk/di_data"
 
# ── Timeouts ─────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 30   # seconds — PRAL can be slow
 
 
class FBRAPIError(Exception):
    """Raised when FBR returns an error response."""
    def __init__(self, error_code: str, message: str, raw_response: dict = None):
        self.error_code = error_code
        self.message    = message
        self.raw_response = raw_response or {}
        super().__init__(f"FBR Error [{error_code}]: {message}")
 
 
class FBRClient:
    """
    Stateless HTTP client for FBR PRAL Digital Invoicing API.
 
    Usage:
        client   = FBRClient(token="your_token", is_sandbox=True)
        response = client.submit_invoice(invoice_payload)
    """
 
    def __init__(self, token: str, base_url: str = None, is_sandbox: bool = False):
        self.token      = token
        self.is_sandbox = is_sandbox
        if not base_url:
            base_url = FBR_SANDBOX_BASE if is_sandbox else FBR_PRODUCTION_BASE
        base = base_url.rstrip('/')
        if not base.endswith('/di_data'):
            base = f"{base}/di_data"
        self.base_url   = base

    def _headers(self) -> dict:
        return {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    def _check_response_errors(self, data: dict):
        """
        Robustly inspect FBR response payload for validation or system errors.
        Handles both top-level error codes and nested validationResponse objects.
        """
        import json
        print("\n" + "="*50)
        print("RAW FBR RESPONSE:")
        print(json.dumps(data, indent=2))
        print("="*50 + "\n")

        if not isinstance(data, dict):
            return

        # 1. Check nested validationResponse (common for WSO2 or FBR validation errors)
        val_resp = data.get("validationResponse")
        if val_resp and isinstance(val_resp, dict):
            status_code = str(val_resp.get("statusCode", ""))
            status = str(val_resp.get("status", "")).lower()
            error_code_val = val_resp.get("errorCode")
            error_code = str(error_code_val) if error_code_val is not None else ""
            
            is_error = False
            if status_code and status_code not in ("00", "0"):
                is_error = True
            elif status and status not in ("valid", "success"):
                is_error = True
            elif error_code and error_code not in ("", "0", "00"):
                is_error = True
                
            if is_error:
                error_msg = val_resp.get("error") or val_resp.get("errorMessage")
                if not error_msg:
                    # Look for item-level errors in invoiceStatuses inside validationResponse
                    for item_status in val_resp.get("invoiceStatuses", []):
                        if str(item_status.get("statusCode", "")) not in ("00", "0"):
                            item_err = item_status.get("error") or item_status.get("errorMessage")
                            if item_err:
                                error_msg = f"Item {item_status.get('itemSNo', '?')}: {item_err}"
                                break
                if not error_msg:
                    error_msg = "Validation failed"
                
                final_code = error_code or status_code or "UNKNOWN"
                logger.error(f"[FBR] Operation failed via validationResponse: [{final_code}] {error_msg}")
                raise FBRAPIError(final_code, error_msg, raw_response=data)

        # 2. Check top-level errorCode (only if present)
        if "errorCode" in data:
            error_code = str(data.get("errorCode", ""))
            if error_code not in ("", "0", "00"):
                error_msg = data.get("errorMessage", "Unknown FBR error")
                logger.error(f"[FBR] Operation failed via top-level: [{error_code}] {error_msg}")
                raise FBRAPIError(error_code, error_msg)

    def submit_invoice(self, payload: dict) -> dict:
        """
        POST /v1/di/postinvoicedata (or postinvoicedata_sb for sandbox)

        Submits one invoice to FBR.

        Args:
            payload: Complete FBR invoice JSON dict
                     (built by FBRInvoiceBuilder.build())

        Returns:
            dict with keys:
              - fbr_invoice_number: str  (e.g. "7000007DI1747119701593")
              - qr_code:            str  (QR code data for receipt)
              - raw_response:       dict (full FBR response)

        Raises:
            FBRAPIError: if FBR returns an error
            ConnectionError: if network is unavailable
        """
        path = "postinvoicedata_sb" if self.is_sandbox else "postinvoicedata"
        url = f"{self.base_url}/v1/di/{path}"
        logger.info(f"[FBR] Submitting invoice to {url}")

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
        except (ConnectionError, Timeout) as e:
            logger.error(f"[FBR] Network error during submission: {e}")
            raise ConnectionError(f"Network error connecting to FBR: {e}")
        except RequestException as e:
            logger.error(f"[FBR] Request error: {e}")
            raise

        logger.info(f"[FBR] Response status: {response.status_code}")
        logger.info(f"[FBR] Response body: {response.text[:500]}")

        import json as _json
        import re as _re
        try:
            # Clean invalid trailing commas that FBR sometimes returns
            clean_text = _re.sub(r',\s*}', '}', response.text)
            clean_text = _re.sub(r',\s*]', ']', clean_text)
            data = _json.loads(clean_text)
        except Exception:
            raise FBRAPIError(
                "PARSE_ERROR",
                f"Could not parse FBR response: {response.text[:500]}"
            )

        # Robustly inspect for errors
        self._check_response_errors(data)

        # Extract the invoice number and QR code
        fbr_invoice_number = data.get("invoiceNumber", "")
        qr_code            = data.get("qrCode", "")

        logger.info(f"[FBR] Invoice submitted successfully: {fbr_invoice_number}")

        return {
            "fbr_invoice_number": fbr_invoice_number,
            "qr_code":            qr_code,
            "raw_response":       data,
        }

    def validate_invoice(self, payload: dict) -> dict:
        """
        POST /v1/di/validateinvoicedata (or validateinvoicedata_sb for sandbox)

        Validates an invoice with FBR without permanently submitting it.
        """
        path = "validateinvoicedata_sb" if self.is_sandbox else "validateinvoicedata"
        url = f"{self.base_url}/v1/di/{path}"
        logger.info(f"[FBR] Validating invoice at {url}")

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
        except (ConnectionError, Timeout) as e:
            logger.error(f"[FBR] Network error during validation: {e}")
            raise ConnectionError(f"Network error connecting to FBR: {e}")
        except RequestException as e:
            logger.error(f"[FBR] Request error: {e}")
            raise

        logger.info(f"[FBR] Validation response status: {response.status_code}")
        logger.info(f"[FBR] Validation response body: {response.text[:500]}")

        import json as _json
        import re as _re
        try:
            clean_text = _re.sub(r',\s*}', '}', response.text)
            clean_text = _re.sub(r',\s*]', ']', clean_text)
            data = _json.loads(clean_text)
        except Exception:
            raise FBRAPIError(
                "PARSE_ERROR",
                f"Could not parse FBR validation response: {response.text[:500]}"
            )

        # Robustly inspect for errors
        self._check_response_errors(data)

        logger.info(f"[FBR] Invoice validated successfully")

        return {
            "status": "Valid",
            "raw_response": data
        }

    def get_invoice(self, fbr_invoice_number: str) -> dict:
        """
        GET /v1/di/getinvoice?invoiceNumber={number}

        Fetches a previously submitted invoice from FBR.
        Used to verify submission status.

        Returns:
            dict — full FBR invoice data
        """
        url = f"{self.base_url}/v1/di/getinvoice"
        logger.info(f"[FBR] Fetching invoice {fbr_invoice_number}")

        try:
            response = requests.get(
                url,
                params={"invoiceNumber": fbr_invoice_number},
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            )
        except (ConnectionError, Timeout) as e:
            raise ConnectionError(f"Network error fetching invoice from FBR: {e}")

        import json as _json
        import re as _re
        try:
            # Clean invalid trailing commas that FBR sometimes returns
            clean_text = _re.sub(r',\s*}', '}', response.text)
            clean_text = _re.sub(r',\s*]', ']', clean_text)
            data = _json.loads(clean_text)
        except Exception:
            raise FBRAPIError(
                "PARSE_ERROR",
                f"Could not parse FBR response: {response.text[:500]}"
            )

        # Robustly inspect for errors
        self._check_response_errors(data)

        return data