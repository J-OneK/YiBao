from __future__ import annotations

import unittest

from jyk.pdf_decl_pipeline_test.aligner import align_and_correct_pdf
from jyk.pdf_decl_pipeline_test.models import PageExtraction, PdfPageModel, PdfWordBox, RecognizedField
from jyk.pdf_decl_pipeline_test.pdf_loader import _compute_render_zoom


class PdfPipelineCoreTests(unittest.TestCase):
    def test_compute_render_zoom_caps_max_side(self):
        base_zoom = 3.0
        z = _compute_render_zoom(base_zoom, width=6000, height=3000, max_side=4096)
        self.assertLess(z, base_zoom)
        self.assertAlmostEqual(z, base_zoom * (4096 / 6000), places=5)

    def test_aligner_prefers_pdf_word_box(self):
        page = PdfPageModel(
            page_index=0,
            image_id=1,
            image_path="",
            image_data_url="",
            image_width=2000,
            image_height=1000,
            pdf_rect=(0.0, 0.0, 600.0, 300.0),
            scale_x=3.3333,
            scale_y=3.3333,
            word_boxes=[
                PdfWordBox(
                    page_index=0,
                    text="SHANGHAI",
                    x=300,
                    y=120,
                    width=180,
                    height=40,
                    block_no=0,
                    line_no=5,
                    word_no=1,
                )
            ],
        )
        extraction = PageExtraction(
            page=page,
            pre_dec_head=[
                RecognizedField(
                    key_desc="境内收发货人名称",
                    key="consigneeCname",
                    value="SHANGHAI",
                    pixel=[500, 500, 700, 700],
                    area="head",
                    source_image_id=1,
                    page_index=0,
                )
            ],
            pre_dec_list=[],
        )
        aligned = align_and_correct_pdf([extraction], att_type_code=4)
        source = aligned["preDecHead"][0]["sourceList"][0]
        self.assertEqual(source["axisX"], 300)
        self.assertEqual(source["axisY"], 120)
        self.assertTrue(source["coordCorrected"])
        self.assertEqual(source["sourceType"], "pdf_word")


if __name__ == "__main__":
    unittest.main()

