import argparse
import os
import re
import time

from PIL import Image, ImageChops
try:
    from PIL import ImageGrab
except Exception:
    ImageGrab = None

try:
    import win32com.client as win32
except Exception:
    win32 = None


def sanitize_filename(name: str) -> str:
    return re.sub(r"[\\/*?:\"<>|]", "_", name)


def points_to_pixels(points: float, dpi: int) -> int:
    return int(points * dpi / 72)


def trim_white_border(image: Image.Image, diff_threshold: int = 10, padding: int = 2) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")

    bg = Image.new("RGB", image.size, (255, 255, 255))
    diff = ImageChops.difference(image, bg).convert("L")
    diff = diff.point(lambda x: 255 if x > diff_threshold else 0)
    bbox = diff.getbbox()

    if not bbox:
        return image

    left, top, right, bottom = bbox
    left = max(left - padding, 0)
    top = max(top - padding, 0)
    right = min(right + padding, image.width)
    bottom = min(bottom + padding, image.height)

    return image.crop((left, top, right, bottom))


def postprocess_image(
    path: str,
    max_width_px: int,
    max_height_px: int,
    trim_white: bool,
    diff_threshold: int,
    padding: int,
) -> None:
    img = Image.open(path)

    if trim_white:
        img = trim_white_border(img, diff_threshold=diff_threshold, padding=padding)

    target_w = max_width_px if max_width_px > 0 else img.width
    target_h = max_height_px if max_height_px > 0 else img.height

    if img.width > target_w or img.height > target_h:
        img.thumbnail((target_w, target_h), Image.LANCZOS)

    img.save(path)


def find_used_range(ws, app):
    used = ws.UsedRange
    first_row = used.Row
    first_col = used.Column
    last_row = first_row + used.Rows.Count - 1
    last_col = first_col + used.Columns.Count - 1

    while last_row >= first_row:
        row_rng = ws.Range(ws.Cells(last_row, first_col), ws.Cells(last_row, last_col))
        if app.WorksheetFunction.CountA(row_rng) == 0:
            last_row -= 1
        else:
            break

    while last_col >= first_col:
        col_rng = ws.Range(ws.Cells(first_row, last_col), ws.Cells(last_row, last_col))
        if app.WorksheetFunction.CountA(col_rng) == 0:
            last_col -= 1
        else:
            break

    if last_row < first_row or last_col < first_col:
        return None

    return first_row, first_col, last_row, last_col


def split_rows_by_height(ws, start_row: int, end_row: int, max_height_px: int, dpi: int):
    chunks = []
    current_start = start_row
    current_height = 0

    for row in range(start_row, end_row + 1):
        row_height_pt = ws.Rows(row).RowHeight
        row_height_px = points_to_pixels(row_height_pt, dpi)
        if current_height + row_height_px > max_height_px and row > current_start:
            chunks.append((current_start, row - 1))
            current_start = row
            current_height = 0
        current_height += row_height_px

    if current_start <= end_row:
        chunks.append((current_start, end_row))

    return chunks


def grab_clipboard_image(retries: int = 8, delay: float = 0.2):
    if ImageGrab is None:
        return None
    for _ in range(retries):
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            return img
        time.sleep(delay)
    return None


def export_range_as_image(rng, output_path: str) -> None:
    ws = rng.Worksheet
    ws.Activate()
    try:
        rng.Select()
    except Exception:
        pass

    try:
        rng.CopyPicture(Appearance=2, Format=2)
    except Exception:
        rng.CopyPicture(Appearance=1, Format=2)
    time.sleep(0.3)

    chart_obj = ws.ChartObjects().Add(0, 0, max(rng.Width, 1), max(rng.Height, 1))
    try:
        chart = chart_obj.Chart
        for _ in range(5):
            try:
                chart.Paste()
                if chart.Shapes().Count > 0:
                    break
            except Exception:
                time.sleep(0.1)
        time.sleep(0.2)
        try:
            chart.Export(output_path, "PNG")
        except Exception:
            chart.Export(output_path)
    except Exception as exc:
        img = grab_clipboard_image()
        if img is None:
            raise exc
        img.save(output_path)
    finally:
        chart_obj.Delete()


def excel_to_images(
    excel_path: str,
    output_dir: str,
    max_height_px: int = 1600,
    max_width_px: int = 2400,
    dpi: int = 96,
    trim_white: bool = True,
    diff_threshold: int = 10,
    padding: int = 2,
    visible: bool = False,
    include_hidden: bool = False,
) -> None:
    if win32 is None:
        raise RuntimeError("pywin32 is required on Windows. Install: pip install pywin32 pillow")

    if not os.path.exists(excel_path):
        raise FileNotFoundError(excel_path)

    os.makedirs(output_dir, exist_ok=True)

    def safe_set(obj, attr, value):
        try:
            setattr(obj, attr, value)
        except Exception:
            pass

    app = None
    try:
        app = win32.gencache.EnsureDispatch("Excel.Application")
    except Exception:
        try:
            app = win32.DispatchEx("Excel.Application")
        except Exception:
            app = win32.Dispatch("Excel.Application")

    if app is None:
        print("Failed to create Excel.Application COM instance.")
        return

    safe_set(app, "Visible", visible)
    safe_set(app, "DisplayAlerts", False)
    safe_set(app, "ScreenUpdating", True)
    safe_set(app, "AskToUpdateLinks", False)

    workbook_path = os.path.abspath(excel_path)
    wb = None

    try:
        try:
            workbooks = app.Workbooks
        except Exception as exc:
            print("Failed to access Excel.Application.Workbooks")
            print(f"  -> {exc}")
            return

        open_attempts = [
            {
                "UpdateLinks": 0,
                "ReadOnly": True,
                "IgnoreReadOnlyRecommended": True,
                "AddToMru": False,
                "CorruptLoad": 1,
            },
            {
                "UpdateLinks": 0,
                "ReadOnly": True,
                "IgnoreReadOnlyRecommended": True,
                "AddToMru": False,
                "CorruptLoad": 2,
            },
            {
                "UpdateLinks": 0,
                "ReadOnly": True,
                "IgnoreReadOnlyRecommended": True,
                "AddToMru": False,
            },
        ]
        last_exc = None
        for kwargs in open_attempts:
            try:
                wb = workbooks.Open(workbook_path, **kwargs)
                if wb is not None:
                    break
            except Exception as exc:
                last_exc = exc
                wb = None

        if wb is None:
            print(f"Failed to open workbook: {workbook_path}")
            if last_exc:
                print(f"  -> {last_exc}")
            return

        for ws in wb.Worksheets:
            sheet_name = ws.Name
            safe_sheet_name = sanitize_filename(sheet_name)
            print(f"Processing sheet: {sheet_name}")

            original_visibility = ws.Visible
            if original_visibility != -1:
                if not include_hidden:
                    print(f"  -> Skip hidden sheet: {sheet_name}")
                    continue
                ws.Visible = -1

            used = find_used_range(ws, app)
            if not used:
                print(f"  -> Skip empty sheet: {sheet_name}")
                if original_visibility != -1:
                    ws.Visible = original_visibility
                continue

            first_row, first_col, last_row, last_col = used
            rng = ws.Range(ws.Cells(first_row, first_col), ws.Cells(last_row, last_col))

            rng.WrapText = True
            rng.EntireColumn.AutoFit()
            rng.EntireRow.AutoFit()

            row_chunks = split_rows_by_height(ws, first_row, last_row, max_height_px, dpi)

            for idx, (row_start, row_end) in enumerate(row_chunks, start=1):
                chunk_rng = ws.Range(ws.Cells(row_start, first_col), ws.Cells(row_end, last_col))
                if len(row_chunks) == 1:
                    filename = f"{safe_sheet_name}.png"
                else:
                    filename = f"{safe_sheet_name}_part_{idx}.png"
                output_path = os.path.join(output_dir, filename)

                export_range_as_image(chunk_rng, output_path)
                postprocess_image(
                    output_path,
                    max_width_px=max_width_px,
                    max_height_px=max_height_px,
                    trim_white=trim_white,
                    diff_threshold=diff_threshold,
                    padding=padding,
                )
                print(f"  -> Saved {output_path}")

            if original_visibility != -1:
                ws.Visible = original_visibility
    finally:
        if wb is not None:
            try:
                wb.Close(False)
            except Exception:
                pass
        try:
            app.Quit()
        except Exception:
            pass


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Excel sheets to images using Excel COM (hidden by default).")
    parser.add_argument("excel_path", help="Path to .xls or .xlsx file")
    parser.add_argument("output_dir", nargs="?", default="result_imgs", help="Output directory")
    parser.add_argument("--max-height", type=int, default=1600, help="Max image height in px")
    parser.add_argument("--max-width", type=int, default=2400, help="Max image width in px")
    parser.add_argument("--dpi", type=int, default=96, help="DPI used for row-height estimation")
    parser.add_argument("--no-trim", action="store_true", help="Disable white border trimming")
    parser.add_argument("--diff-threshold", type=int, default=10, help="White trim sensitivity")
    parser.add_argument("--padding", type=int, default=2, help="Padding after trimming")
    parser.add_argument("--visible", action="store_true", help="Show Excel window while rendering")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden sheets in export")
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    excel_to_images(
        args.excel_path,
        args.output_dir,
        max_height_px=args.max_height,
        max_width_px=args.max_width,
        dpi=args.dpi,
        trim_white=not args.no_trim,
        diff_threshold=args.diff_threshold,
        padding=args.padding,
        visible=args.visible,
        include_hidden=args.include_hidden,
    )
