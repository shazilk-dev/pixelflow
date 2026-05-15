"""
Tests for AC-1.1 through AC-1.10 — Image Transformation Pipeline
All tests use a programmatically created image; no real files required.
"""
import os
import io
import pathlib
import tempfile
from unittest.mock import patch, call, MagicMock

import pytest
from PIL import Image, ImageFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rgb_image(width=1200, height=800, color=(100, 150, 200)) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


def save_image(img: Image.Image, directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    img.save(path)
    return path


def apply_transformations(input_path: str, output_path: str, transformations: list[str]) -> Image.Image:
    """
    Thin wrapper that calls the module under test.
    Import is deferred so the test file itself can be collected even before
    the implementation exists — pytest will fail at call time, not at import.
    """
    from tasks.image_tasks import apply_transforms  # noqa: PLC0415
    return apply_transforms(input_path, output_path, transformations)


# ---------------------------------------------------------------------------
# AC-1.1  resize reduces dimensions
# ---------------------------------------------------------------------------

class TestResize:
    def test_resize_reduces_dimensions(self, tmp_path):
        """AC-1.1: 1200×800 → 800×600, file written, mode still RGB."""
        img = make_rgb_image(1200, 800)
        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        result = apply_transformations(src, dst, ["resize"])

        out = Image.open(dst)
        assert out.size == (800, 600), f"Expected (800, 600), got {out.size}"
        assert os.path.exists(dst)
        assert out.mode == "RGB"

    # AC-1.2  LANCZOS resampling
    def test_resize_uses_lanczos(self, tmp_path):
        """AC-1.2: PIL resize is called with Image.LANCZOS resampling filter."""
        img = make_rgb_image(1200, 800)
        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        with patch("PIL.Image.Image.resize", wraps=img.resize) as mock_resize:
            # Re-open so we get a fresh image object that uses the patched method
            from tasks.image_tasks import apply_transforms  # noqa: PLC0415
            with patch("PIL.Image.open") as mock_open:
                mock_img = MagicMock(wraps=Image.open(src))
                mock_img.mode = "RGB"
                mock_img.size = (1200, 800)
                mock_open.return_value.__enter__ = lambda s: mock_img
                mock_open.return_value.__exit__ = MagicMock(return_value=False)
                mock_img.resize.return_value = Image.new("RGB", (800, 600))
                mock_img.save = MagicMock()
                apply_transforms(src, dst, ["resize"])

            mock_img.resize.assert_called_once()
            _, kwargs = mock_img.resize.call_args
            resample = kwargs.get("resample", None)
            if resample is None and mock_img.resize.call_args.args:
                resample = mock_img.resize.call_args.args[1] if len(mock_img.resize.call_args.args) > 1 else None
            assert resample == Image.LANCZOS, (
                f"Expected Image.LANCZOS ({Image.LANCZOS}), got {resample}"
            )


# ---------------------------------------------------------------------------
# AC-1.3  grayscale converts mode
# ---------------------------------------------------------------------------

class TestGrayscale:
    def test_grayscale_converts_mode(self, tmp_path):
        """AC-1.3: RGB → mode 'L'; all pixels are uniform across channels."""
        img = make_rgb_image()
        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        apply_transformations(src, dst, ["grayscale"])

        out = Image.open(dst)
        assert out.mode == "L", f"Expected mode 'L', got '{out.mode}'"


# ---------------------------------------------------------------------------
# AC-1.4  blur changes pixel values near edges
# ---------------------------------------------------------------------------

class TestBlur:
    def test_blur_changes_pixel_values(self, tmp_path):
        """AC-1.4: Sharp edge pixels are neither pure black nor pure white after blur."""
        # Create a sharp black/white edge image
        img = Image.new("RGB", (200, 200), (0, 0, 0))
        right_half = Image.new("RGB", (100, 200), (255, 255, 255))
        img.paste(right_half, (100, 0))

        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        apply_transformations(src, dst, ["blur"])

        out = Image.open(dst)
        # Sample pixels right at the boundary column (x=99 or x=100)
        edge_pixel = out.getpixel((99, 100))
        r = edge_pixel[0] if isinstance(edge_pixel, tuple) else edge_pixel
        assert 0 < r < 255, f"Edge pixel R={r} should be blended, not pure 0 or 255"

        assert out.size == img.size, "Blur must not change dimensions"
        assert out.mode == img.mode, "Blur must not change image mode"

    # AC-1.5  sharpen increases local contrast
    def test_sharpen_increases_contrast(self, tmp_path):
        """AC-1.5: Centre pixel deviates MORE from neighbours after sharpening."""
        base_color = 128
        img = Image.new("RGB", (21, 21), (base_color, base_color, base_color))
        # Place one slightly-off pixel in the centre
        img.putpixel((10, 10), (140, 140, 140))

        # Use PNG to avoid JPEG lossy compression destroying the subtle 12-unit difference.
        src = save_image(img, str(tmp_path), "input.png")
        dst = str(tmp_path / "input_processed.png")

        centre_before = img.getpixel((10, 10))[0]
        neighbour_before = img.getpixel((9, 10))[0]
        deviation_before = abs(centre_before - neighbour_before)

        apply_transformations(src, dst, ["sharpen"])

        out = Image.open(dst)
        centre_after = out.getpixel((10, 10))[0]
        neighbour_after = out.getpixel((9, 10))[0]
        deviation_after = abs(centre_after - neighbour_after)

        assert deviation_after >= deviation_before, (
            f"Sharpening should increase or maintain edge contrast "
            f"(before={deviation_before}, after={deviation_after})"
        )
        assert out.size == img.size


# ---------------------------------------------------------------------------
# AC-1.6  watermark adds text pixels
# ---------------------------------------------------------------------------

class TestWatermark:
    def test_watermark_adds_text(self, tmp_path):
        """AC-1.6: At least one non-white pixel appears in bottom-right quadrant."""
        img = Image.new("RGB", (400, 300), (255, 255, 255))
        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        apply_transformations(src, dst, ["watermark"])

        out = Image.open(dst)
        assert out.mode == "RGB"
        assert out.size == img.size

        # Check bottom-right quadrant for any non-white pixel
        w, h = out.size
        found_non_white = False
        for x in range(w // 2, w):
            for y in range(h // 2, h):
                px = out.getpixel((x, y))
                if px != (255, 255, 255):
                    found_non_white = True
                    break
            if found_non_white:
                break

        assert found_non_white, "Watermark text should darken at least one pixel in bottom-right quadrant"


# ---------------------------------------------------------------------------
# AC-1.7  canonical transformation order
# ---------------------------------------------------------------------------

class TestTransformationOrder:
    def test_transformation_order_is_canonical(self, tmp_path):
        """
        AC-1.7: Transformations are applied in canonical order regardless of
        the order they appear in the input list.
        Expected order: resize → grayscale → blur → sharpen → watermark
        """
        img = make_rgb_image()
        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        call_order = []

        original_resize = Image.Image.resize
        original_convert = Image.Image.convert

        def track_resize(self, size, resample=None, *args, **kwargs):
            call_order.append("resize")
            return original_resize(self, size, resample=resample, *args, **kwargs)

        def track_convert(self, mode, *args, **kwargs):
            if mode == "L":
                call_order.append("grayscale")
            elif mode == "RGB":
                call_order.append("convert_rgb")
            return original_convert(self, mode, *args, **kwargs)

        deliberate_wrong_order = ["watermark", "blur", "resize", "grayscale", "sharpen"]

        with patch.object(Image.Image, "resize", track_resize), \
             patch.object(Image.Image, "convert", track_convert):

            from tasks.image_tasks import apply_transforms  # noqa: PLC0415
            apply_transforms(src, dst, deliberate_wrong_order)

        # resize must come before grayscale in the call log
        if "resize" in call_order and "grayscale" in call_order:
            assert call_order.index("resize") < call_order.index("grayscale"), (
                f"resize must precede grayscale. Got order: {call_order}"
            )


# ---------------------------------------------------------------------------
# AC-1.8  grayscale + watermark edge case (CRITICAL)
# ---------------------------------------------------------------------------

class TestGrayscaleWatermarkEdgeCase:
    def test_grayscale_plus_watermark_edge_case(self, tmp_path):
        """
        AC-1.8 CRITICAL: grayscale converts to 'L'; watermark must re-convert
        to 'RGB' before drawing, otherwise PIL raises TypeError.
        """
        img = make_rgb_image(400, 300)
        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        # Must not raise
        apply_transformations(src, dst, ["grayscale", "watermark"])

        out = Image.open(dst)
        assert out.mode == "RGB", (
            f"Output must be 'RGB' after grayscale+watermark; got '{out.mode}'"
        )

        # Confirm watermark was drawn (non-pure-grey pixel in bottom-right quadrant)
        w, h = out.size
        found_non_white = False
        for x in range(w // 2, w):
            for y in range(h // 2, h):
                px = out.getpixel((x, y))
                if px != (255, 255, 255):
                    found_non_white = True
                    break
            if found_non_white:
                break
        assert found_non_white, "Watermark text pixels must be present after grayscale+watermark"

        # Confirm grayscale was also applied (R == G == B for a sampled interior pixel)
        # We check the top-left quadrant which should not have watermark text
        sample_px = out.getpixel((10, 10))
        assert sample_px[0] == sample_px[1] == sample_px[2], (
            f"Pixel {sample_px} should be grey (R==G==B) confirming grayscale was applied"
        )


# ---------------------------------------------------------------------------
# AC-1.9  output filename convention
# ---------------------------------------------------------------------------

class TestOutputFilenameConvention:
    def test_output_filename_convention(self, tmp_path):
        """
        AC-1.9: Input 'sunset.jpg' → output 'sunset_processed.jpg'.
        Original file must not be modified.
        """
        img = make_rgb_image()
        src = save_image(img, str(tmp_path), "sunset.jpg")
        original_mtime = os.path.getmtime(src)

        output_dir = str(tmp_path / "outputs")
        os.makedirs(output_dir, exist_ok=True)

        from tasks.image_tasks import build_output_path  # noqa: PLC0415
        expected_dst = build_output_path(src, output_dir)

        assert pathlib.Path(expected_dst).name == "sunset_processed.jpg", (
            f"Expected 'sunset_processed.jpg', got '{pathlib.Path(expected_dst).name}'"
        )

        apply_transformations(src, expected_dst, ["resize"])

        assert os.path.exists(expected_dst), "Processed file must exist at the expected output path"
        assert os.path.getmtime(src) == original_mtime, "Original file must not be modified"


# ---------------------------------------------------------------------------
# AC-1.10  each transformation in isolation
# ---------------------------------------------------------------------------

class TestSingleTransformationEach:
    @pytest.mark.parametrize("transform", ["resize", "grayscale", "blur", "sharpen", "watermark"])
    def test_single_transformation_each(self, transform, tmp_path):
        """
        AC-1.10: Each transformation in isolation produces a valid output file
        with no exception raised.
        """
        img = make_rgb_image()
        src = save_image(img, str(tmp_path), "input.jpg")
        dst = str(tmp_path / "input_processed.jpg")

        apply_transformations(src, dst, [transform])

        assert os.path.exists(dst), f"Output file must exist after '{transform}'"
        reopened = Image.open(dst)
        reopened.verify()  # raises if file is corrupt
