"""Régression des transferts lents et de la reprise après perte d’accusé."""
import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from cahpp_app.horizon.mobile_catalog import CatalogTransferPaused, publish_catalog
from cahpp_app.horizon.mobile_sync import Relay, RelayNetworkError


class CatalogTransferTest(unittest.TestCase):
    def test_compression_fits_a_limited_upload_and_preserves_exact_records(self):
        relay = Relay("https://relay.test", "private-token")
        relay.catalog_gzip = True
        products = [{"code": f"ART-{i}", "label": "Compresses stériles de soin" * 4,
                     "supplier": "Fournisseur de test", "fingerprint": f"{i:064x}"} for i in range(2000)]
        raw = json.dumps(products).encode()
        uploaded = []

        def limited_upload(request, timeout):
            # Un débit limité refuse l’ancien bloc brut, mais accepte son équivalent compressé.
            self.assertLess(len(request.data), len(raw) // 4)
            self.assertEqual(request.get_header("Content-encoding"), "gzip")
            self.assertEqual(timeout, 90)
            uploaded.extend(json.loads(gzip.decompress(request.data)))
            return io.BytesIO(b"{}")

        with patch.object(relay.opener, "open", side_effect=limited_upload):
            relay.call("catalog-sync/" + "a" * 64 + "/0", products)
        self.assertEqual(uploaded, products)
        for route in ("orders/order-id", "catalog-sync/" + "a" * 64):
            if route.startswith("catalog-sync"):
                relay.catalog_gzip = False  # Relais historique sans cette capacité.
            with patch.object(relay.opener, "open", return_value=io.BytesIO(b"{}")) as opened:
                relay.call(route, products)
                self.assertIsNone(opened.call_args.args[0].get_header("Content-encoding"))
                self.assertEqual(json.loads(opened.call_args.args[0].data), products)
                self.assertEqual(opened.call_args.kwargs["timeout"], 90 if route.startswith("catalog-sync") else 30)

    def test_timeout_is_identified_without_disclosing_socket_message_or_token(self):
        relay = Relay("https://relay.test", "private-token")
        error = URLError(TimeoutError("The write operation timed out private-token"))
        with patch.object(relay.opener, "open", side_effect=error), self.assertLogs(
                "cahpp_app.horizon.mobile_sync", level="INFO") as logs:
            with self.assertRaises(RelayNetworkError) as caught:
                relay.call("catalog-sync/" + "a" * 64 + "/16", [{}])
        self.assertEqual(caught.exception.network_cause, "timeout")
        self.assertIn("bloc 17", str(caught.exception))
        self.assertIn("cause=timeout", " ".join(logs.output))
        self.assertNotIn("private-token", str(caught.exception) + " ".join(logs.output))

    def test_lost_ack_resumes_existing_generation_and_skips_received_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"generation": "a" * 64, "parts": 2, "count": 2, "suppliers": []}
            (root / "0.json").write_text('[{"code":"one"}]')
            (root / "1.json").write_text('[{"code":"two"}]')

            class Remote:
                received = set()
                sent = []
                active = ""
                fail = True

                def call(self, route, body=None):
                    if route == "mobile-state":
                        return {"catalog": self.active, "catalog_gzip": True}
                    if body is None:
                        return {"parts": sorted(self.received)}
                    if isinstance(body, list):
                        part = int(route.rsplit("/", 1)[1])
                        self.sent.append(part)
                        self.received.add(part)
                        if self.fail:
                            self.fail = False
                            raise URLError(TimeoutError("Accusé perdu"))
                    elif route.endswith("/commit"):
                        self.active = manifest["generation"]
                    return {}

            remote = Remote()
            with patch("cahpp_app.horizon.mobile_catalog.catalog_cache", return_value=(root, manifest)):
                with self.assertRaisesRegex(CatalogTransferPaused, "0/2 blocs confirmés"):
                    publish_catalog(None, remote)
                self.assertIn("publié", publish_catalog(None, remote))
                self.assertEqual(remote.sent, [0, 1])
                self.assertTrue(remote.catalog_gzip)
                self.assertEqual(publish_catalog(None, remote), "")

    def test_slow_transfer_yields_between_blocks_without_restarting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"generation": "a" * 64, "parts": 2, "count": 2, "suppliers": []}
            for i in range(2):
                (root / f"{i}.json").write_text("[{}]")
            relay = unittest.mock.Mock()
            relay.call.side_effect = [{"catalog": ""}, {"parts": []}, {}, {}]
            with patch("cahpp_app.horizon.mobile_catalog.catalog_cache", return_value=(root, manifest)), patch(
                    "cahpp_app.horizon.mobile_catalog.time.monotonic", side_effect=[0, 21]):
                self.assertIn("1/2 blocs", publish_catalog(None, relay))
            self.assertEqual(relay.call.call_count, 4)


if __name__ == "__main__":
    unittest.main()
