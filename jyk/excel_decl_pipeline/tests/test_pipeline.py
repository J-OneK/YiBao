from __future__ import annotations

import unittest
from pathlib import Path
import shutil

from PIL import Image

from jyk.excel_decl_pipeline.aligner import align_and_correct
from jyk.excel_decl_pipeline.models import CellBox, Chunk, ChunkExtraction, RecognizedField, RenderedSheet
from jyk.excel_decl_pipeline.splitter import split_rendered_sheet


class PipelineCoreTests(unittest.TestCase):
    def test_split_respects_max_side(self):
        rendered = RenderedSheet(
            sheet_name="Sheet1",
            sheet_index=0,
            image=Image.new("RGB", (5000, 5000), "white"),
            row_heights_px=[1200, 1200, 1200, 1200, 200],
            col_widths_px=[1600, 1600, 1600, 200],
            cell_boxes={},
        )
        tmpdir = Path("d:/code/YiBao/jyk/excel_decl_pipeline/tests/.tmp_chunks")
        if tmpdir.exists():
            shutil.rmtree(tmpdir)
        tmpdir.mkdir(parents=True, exist_ok=True)
        try:
            chunks = split_rendered_sheet(
                rendered=rendered,
                max_side=4096,
                image_id_start=1,
                chunk_output_dir=tmpdir,
            )
        finally:
            if tmpdir.exists():
                shutil.rmtree(tmpdir)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(chunk.width, 4096)
            self.assertLessEqual(chunk.height, 4096)

    def test_coordinate_correction_prefers_excel_cell(self):
        chunk = Chunk(
            chunk_id="s:0-0:0-0",
            image_id=1,
            sheet_name="Sheet1",
            sheet_index=0,
            row_range=(0, 0),
            col_range=(0, 0),
            offset_x=0,
            offset_y=0,
            width=1000,
            height=600,
            image=Image.new("RGB", (1000, 600), "white"),
            image_data_url="data:image/png;base64,",
            image_path="",
            cell_boxes=[
                CellBox(
                    sheet_name="Sheet1",
                    sheet_index=0,
                    row=2,
                    col=3,
                    row_span=1,
                    col_span=1,
                    text="ABC123",
                    x=100,
                    y=200,
                    width=220,
                    height=50,
                )
            ],
            row_heights_px=[300, 300, 300],
            col_widths_px=[400, 400, 400],
        )
        extraction = ChunkExtraction(
            chunk=chunk,
            pre_dec_head=[
                RecognizedField(
                    key_desc="商品编号",
                    key="codeTs",
                    value="ABC123",
                    pixel=[500, 500, 700, 700],
                    area="head",
                    source_image_id=1,
                )
            ],
            pre_dec_list=[],
        )
        aligned = align_and_correct([extraction], att_type_code=4)
        source = aligned["preDecHead"][0]["sourceList"][0]
        self.assertEqual(source["axisX"], 100)
        self.assertEqual(source["axisY"], 200)
        self.assertTrue(source["coordCorrected"])


if __name__ == "__main__":
    unittest.main()
