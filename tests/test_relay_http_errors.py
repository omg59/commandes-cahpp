import io
import unittest
from email.message import Message
from urllib.error import HTTPError
from unittest.mock import patch

from cahpp_app.horizon.mobile_sync import Relay, RelayHTTPError


class RelayErrorTest(unittest.TestCase):
    def test_proxy_refusal_has_http_code_and_no_raw_body_or_key(self):
        headers = Message()
        headers["Content-Type"] = "text/html"
        error = HTTPError("https://relay.test/v1/versions", 403, "Forbidden", headers,
                          io.BytesIO(b"<html>private-data</html>"))
        relay = Relay("https://relay.test", "secret-key")
        with patch.object(relay.opener, "open", side_effect=error):
            with self.assertRaises(RelayHTTPError) as caught:
                relay.call("versions")
        self.assertIn("HTTP 403 sur /v1/versions", str(caught.exception))
        self.assertIn("Nginx Proxy Manager", str(caught.exception))
        self.assertEqual(caught.exception.http_origin, "html")
        self.assertNotIn("private-data", str(caught.exception))
        self.assertNotIn("secret-key", str(caught.exception))

    def test_relay_key_refusal_has_specific_explanation(self):
        headers = Message()
        headers["Content-Type"] = "application/json"
        error = HTTPError("https://relay.test/v1/versions", 401, "Unauthorized", headers,
                          io.BytesIO('{"error":"Clé invalide."}'.encode()))
        failure = RelayHTTPError(error, "versions")
        self.assertIn("HORIZON_PC_TOKEN", str(failure))
        self.assertEqual(failure.http_origin, "relay")
