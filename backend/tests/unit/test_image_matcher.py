"""Unit tests for perceptual image hashing, visual vectors, and similarity scoring."""

import io
from PIL import Image, ImageDraw
import pytest

from app.services.image_matcher import (
    compute_ahash,
    compute_dhash,
    compute_image_fingerprint,
    compute_visual_vector,
    hamming_distance,
    visual_similarity_score,
)


def _make_test_image(pattern: str = "rect", color: str = "red", size: tuple[int, int] = (120, 120)) -> Image.Image:
    im = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(im)
    if pattern == "rect":
        draw.rectangle([10, 10, 60, 60], fill=color)
    elif pattern == "circle":
        draw.ellipse([20, 20, 100, 100], fill=color)
    elif pattern == "cross":
        draw.line([10, 10, 110, 110], fill=color, width=8)
        draw.line([10, 110, 110, 10], fill=color, width=8)
    return im


def test_dhash_and_ahash_identical_for_same_image():
    im = _make_test_image("rect", "blue")
    h1 = compute_dhash(im)
    h2 = compute_dhash(im)
    assert h1 == h2
    assert len(h1) == 16  # 64 bits = 16 hex chars
    assert hamming_distance(h1, h2) == 0


def test_dhash_resilient_to_jpeg_recompression():
    im = _make_test_image("circle", "green")
    h_orig = compute_dhash(im)

    # Save to JPEG buffer and reload
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    buf.seek(0)
    im_reloaded = Image.open(buf)
    h_jpeg = compute_dhash(im_reloaded)

    dist = hamming_distance(h_orig, h_jpeg)
    assert dist <= 3  # Virtually zero drift under standard compression


def test_dhash_resilient_to_resize():
    im_base = _make_test_image("rect", "purple", size=(200, 200))
    im_small = im_base.resize((80, 80))
    im_large = im_base.resize((500, 500))

    h1 = compute_dhash(im_small)
    h2 = compute_dhash(im_large)
    dist = hamming_distance(h1, h2)
    assert dist <= 2


def test_different_images_have_large_hamming_distance():
    im1 = _make_test_image("circle", "blue")
    im2 = _make_test_image("cross", "red")

    h1 = compute_dhash(im1)
    h2 = compute_dhash(im2)
    dist = hamming_distance(h1, h2)
    assert dist >= 12  # Clearly distinct


def test_visual_similarity_score_bounds():
    im1 = _make_test_image("rect", "blue")
    im2 = _make_test_image("circle", "green")

    fp1 = compute_image_fingerprint(im1)
    fp2 = compute_image_fingerprint(im2)

    # Identical images score 1.0
    self_score = visual_similarity_score(fp1, fp1)
    assert self_score >= 0.98

    # Completely different images score low
    diff_score = visual_similarity_score(fp1, fp2)
    assert diff_score < 0.60


def test_visual_vector_normalized():
    im = _make_test_image("cross", "orange")
    vec = compute_visual_vector(im)
    assert len(vec) == 64
    mag = sum(x * x for x in vec)
    assert pytest.approx(mag, 0.05) == 1.0
