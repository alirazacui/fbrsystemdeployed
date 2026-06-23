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
FBR_SANDBOX_BASE    = "https://esp.pral.com.pk/di_data"
FBR_PRODUCTION_BASE = "https://gw.fbr.gov.pk/di_data"
 
# ── Timeouts ─────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 30   # seconds — PRAL can be slow
 
 
class FBRAPIError(Exception):
    """Raised when FBR returns an error response."""
    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message    = message
        super().__init__(f"FBR Error [{error_code}]: {message}")
 
 
class FBRClient:
    """
    Stateless HTTP client for FBR PRAL Digital Invoicing API.
 
    Usage:
        client   = FBRClient(token="your_token", is_sandbox=True)
        response = client.submit_invoice(invoice_payload)
    """
 
    def __init__(self, token: str, is_sandbox: bool = True):
        self.token      = token
        self.is_sandbox = is_sandbox
        self.base_url   = FBR_SANDBOX_BASE if is_sandbox else FBR_PRODUCTION_BASE
 
    def _headers(self) -> dict:
        return {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {self.token}",
        }
 
    def submit_invoice(self, payload: dict) -> dict:
        """
        POST /v1/di/postinvoicedata
 
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
        url = f"{self.base_url}/v1/di/postinvoicedata"
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
        logger.debug(f"[FBR] Response body: {response.text[:500]}")
 
        try:
            data = response.json()
        except Exception:
            raise FBRAPIError(
                "PARSE_ERROR",
                f"Could not parse FBR response: {response.text[:200]}"
            )
 
        # FBR returns errorCode "0" for success
        error_code = str(data.get("errorCode", ""))
        if error_code != "0":
            error_msg = data.get("errorMessage", "Unknown FBR error")
            logger.error(f"[FBR] Submission failed: [{error_code}] {error_msg}")
            raise FBRAPIError(error_code, error_msg)
 
        # Extract the invoice number and QR code
        fbr_invoice_number = data.get("invoiceNumber", "")
        qr_code            = data.get("qrCode", "")
 
        logger.info(f"[FBR] Invoice submitted successfully: {fbr_invoice_number}")
 
        return {
            "fbr_invoice_number": fbr_invoice_number,
            "qr_code":            qr_code,
            "raw_response":       data,
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
 
        try:
            data = response.json()
        except Exception:
            raise FBRAPIError(
                "PARSE_ERROR",
                f"Could not parse FBR response: {response.text[:200]}"
            )
 
        error_code = str(data.get("errorCode", ""))
        if error_code != "0":
            raise FBRAPIError(
                error_code,
                data.get("errorMessage", "Unknown FBR error")
            )
 
        return data