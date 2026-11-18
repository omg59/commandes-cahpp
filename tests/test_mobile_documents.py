import io
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from PIL import Image

from cahpp_app.horizon.mobile_documents import check_mobile_attachment, validate_document


class MobileDocumentTest(unittest.TestCase):
    def test_existing_shared_attachment_requires_allowed_extension_and_matching_content(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / f"facture-{uuid4()}.dat"
            original.write_bytes(b"Document de test")
            with self.assertRaisesRegex(ValueError, "Extension"):
                check_mobile_attachment(original, original.name)
            original = original.rename(original.with_suffix(".pdf"))
            with self.assertRaisesRegex(ValueError, "contenu"):
                check_mobile_attachment(original, original.name)

    def test_pc_checks_actual_image_format(self):
        png = io.BytesIO()
        with Image.new("RGB", (10, 10)) as image:
            image.save(png, "PNG")
        validate_document(png.getvalue(), "image/png")
        with self.assertRaisesRegex(ValueError, "contenu"):
            validate_document(png.getvalue(), "image/jpeg")
