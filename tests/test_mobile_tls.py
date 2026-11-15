"""Vérifier la confiance TLS et le nom d'hôte sur un serveur local."""
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from urllib.error import URLError
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from cahpp_app.horizon.mobile_sync import Relay


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL requis pour créer le certificat de test")
class RelayTlsTest(unittest.TestCase):
    def test_unknown_certificate_is_rejected_then_trusted_bundle_is_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            certificate = root / "certificate.pem"
            key = root / "key.pem"
            subprocess.run(
                ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                 "-keyout", str(key), "-out", str(certificate), "-days", "1",
                 "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                 "-addext", "basicConstraints=critical,CA:TRUE"],
                check=True, capture_output=True,
            )
            requests = []

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    requests.append(self.headers.get("Authorization"))
                    body = json.dumps([]).encode()
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            server = HTTPServer(("127.0.0.1", 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certificate, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"https://localhost:{server.server_port}"
                with self.assertRaisesRegex(ValueError, "certificat HTTPS"):
                    Relay(url, "test-key").call("orders")
                self.assertEqual(requests, [])
                with patch("cahpp_app.horizon.mobile_sync.certifi.where", return_value=str(certificate)):
                    with patch.dict(os.environ, {
                        "https_proxy": "http://127.0.0.1:1",
                        "HTTPS_PROXY": "http://127.0.0.1:1",
                        "no_proxy": "", "NO_PROXY": "",
                    }):
                        self.assertEqual(Relay(url, "test-key").call("orders"), [])
                        with self.assertRaises(URLError):
                            Relay(url, "test-key", use_system_proxy=True).call("orders")
                    with self.assertRaisesRegex(ValueError, "certificat HTTPS"):
                        Relay(url.replace("localhost", "127.0.0.1"), "test-key").call("orders")
                self.assertEqual(requests, ["Bearer test-key"])
            finally:
                server.shutdown()
                worker.join()
                server.server_close()
