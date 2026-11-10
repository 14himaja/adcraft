"""Image recognition and perceptual visual matching for AdCraft DM Agent.

Provides perceptual hashing (dHash, aHash), spatial color/luminance feature vectors,
safe image ingestion/fetching, and robust image-to-post matching.
"""

import io
import math
from typing import Any
from bson import ObjectId
from PIL import Image
import httpx
import structlog

from app.services.embeddings import cosine_similarity

log = structlog.get_logger()

# Constants
DHASH_SIZE = 8  # 8x8 comparisons = 64 bits = 16 hex chars
AHASH_SIZE = 8  # 8x8 pixels = 64 bits = 16 hex chars
MAX_HAMMING_MATCH = 10  # <= 10 bits distance out of 64 is considered a match
AMBIGUITY_DELTA = 3  # If second best is within 3 bits, treat as ambiguous
FETCH_TIMEOUT = 10.0  # Seconds to wait for CDN image download
MAX_IMAGE_BYTES = 12 * 1024 * 1024  # 12 MB max download


def compute_dhash(img: Image.Image, hash_size: int = DHASH_SIZE) -> str:
    """Computes difference hash (dHash) as a 16-character hexadecimal string (64 bits).
    
    dHash tracks relative brightness gradients horizontally across adjacent pixels,
    making it resilient to scale, aspect ratio preservation, and slight color shift.
    """
    # Resize to (hash_size + 1, hash_size)
    resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = resized.load()
    num = 0
    for y in range(hash_size):
        for x in range(hash_size):
            bit = 1 if pixels[x, y] > pixels[x + 1, y] else 0
            num = (num << 1) | bit
    return f"{num:016x}"


def compute_ahash(img: Image.Image, hash_size: int = AHASH_SIZE) -> str:
    """Computes average hash (aHash) as a 16-character hexadecimal string (64 bits).
    
    aHash compares each pixel to the mean luminance across the entire resized image.
    """
    resized = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = resized.load()
    total = sum(pixels[x, y] for y in range(hash_size) for x in range(hash_size))
    avg = total / (hash_size * hash_size)
    num = 0
    for y in range(hash_size):
        for x in range(hash_size):
            bit = 1 if pixels[x, y] > avg else 0
            num = (num << 1) | bit
    return f"{num:016x}"


def compute_visual_vector(img: Image.Image, dim: int = 64) -> list[float]:
    """Generates a normalized 64-dimensional dense visual feature vector.
    
    Combines 4x4 spatial luminance blocks (16 dims) and 48-dim color distribution
    (16 bins each for R, G, B normalized channels) to capture visual layout and palette.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    
    # 1. 4x4 block luminance (16 values)
    lum_img = rgb.convert("L").resize((4, 4), Image.Resampling.BILINEAR)
    lum_pix = lum_img.load()
    lum_vals = [float(lum_pix[x, y]) / 255.0 for y in range(4) for x in range(4)]
    
    # 2. 16 bins per channel (48 values)
    r_hist = [0.0] * 16
    g_hist = [0.0] * 16
    b_hist = [0.0] * 16
    
    # Sample up to 1000 pixels for fast histogram
    step = max(1, (w * h) // 1000)
    sampled = 0
    pixels = rgb.load()
    for y in range(0, h, max(1, int(math.isqrt(step)))):
        for x in range(0, w, max(1, int(math.isqrt(step)))):
            r, g, b = pixels[x, y]
            r_hist[min(15, r // 16)] += 1.0
            g_hist[min(15, g // 16)] += 1.0
            b_hist[min(15, b // 16)] += 1.0
            sampled += 1
            if sampled >= 1000:
                break
        if sampled >= 1000:
            break
            
    if sampled > 0:
        r_hist = [v / sampled for v in r_hist]
        g_hist = [v / sampled for v in g_hist]
        b_hist = [v / sampled for v in b_hist]
        
    vec = lum_vals + r_hist + g_hist + b_hist  # 16 + 16 + 16 + 16 = 64 dims
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        return [round(x / norm, 6) for x in vec]
    return [0.0] * dim


def compute_image_fingerprint(img: Image.Image) -> dict[str, Any]:
    """Extracts a comprehensive visual fingerprint for indexing or query comparison."""
    w, h = img.size
    dhash = compute_dhash(img)
    ahash = compute_ahash(img)
    vec = compute_visual_vector(img)
    return {
        "dhash": dhash,
        "ahash": ahash,
        "visual_vector": vec,
        "aspect_ratio": round(w / max(1, h), 2),
        "dimensions": [w, h],
    }


def hamming_distance(h1: str, h2: str) -> int:
    """Calculates bitwise Hamming distance between two hexadecimal hash strings."""
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except (ValueError, TypeError):
        return 64


def visual_similarity_score(fp1: dict, fp2: dict) -> float:
    """Computes normalized visual match confidence (0.0 to 1.0).
    
    Balances dHash distance (60%), aHash distance (20%), and visual vector cosine (20%).
    """
    h_dist_d = hamming_distance(fp1.get("dhash", ""), fp2.get("dhash", ""))
    h_dist_a = hamming_distance(fp1.get("ahash", ""), fp2.get("ahash", ""))
    
    # 0 distance -> 1.0 score, 16+ distance -> 0.0 score
    d_score = max(0.0, 1.0 - (h_dist_d / 20.0))
    a_score = max(0.0, 1.0 - (h_dist_a / 20.0))
    
    v1 = fp1.get("visual_vector") or []
    v2 = fp2.get("visual_vector") or []
    vec_score = max(0.0, cosine_similarity(v1, v2)) if (v1 and v2) else d_score
    
    return round(0.60 * d_score + 0.20 * a_score + 0.20 * vec_score, 3)


def load_image_from_bytes(data: bytes) -> Image.Image:
    """Safely loads a PIL Image from raw bytes."""
    return Image.open(io.BytesIO(data))


async def fetch_image_from_gridfs(db, image_id: str | ObjectId) -> Image.Image | None:
    """Loads an image from MongoDB GridFS bucket 'images'."""
    try:
        from gridfs import AsyncGridFSBucket
        oid = ObjectId(str(image_id))
        bucket = AsyncGridFSBucket(db, bucket_name="images")
        stream = await bucket.open_download_stream(oid)
        data = await stream.read()
        return load_image_from_bytes(data)
    except Exception as exc:
        log.warning("fetch_image_from_gridfs_failed", image_id=str(image_id), error=str(exc))
        return None


async def fetch_image_from_url(url: str, timeout: float = FETCH_TIMEOUT) -> Image.Image | None:
    """Downloads an image from a public or CDN URL."""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) <= MAX_IMAGE_BYTES:
                return load_image_from_bytes(resp.content)
    except Exception as exc:
        log.warning("fetch_image_from_url_failed", url=url[:100], error=str(exc))
    return None


async def extract_image_from_attachment(db, attachment: dict) -> tuple[Image.Image | None, str | None]:
    """Extracts PIL image and source identifier from a webhook attachment.
    
    Supports:
    - payload.url (Instagram/Facebook CDN URL)
    - payload.image_id (Internal GridFS reference)
    - payload.media_id (Platform media reference)
    - raw_bytes in payload (test environments)
    """
    payload = attachment.get("payload") or {}
    
    # 1. Direct test payload bytes or Image object
    if "image_bytes" in payload and isinstance(payload["image_bytes"], bytes):
        try:
            return load_image_from_bytes(payload["image_bytes"]), "payload_bytes"
        except Exception:
            pass
            
    if "image_obj" in payload and isinstance(payload["image_obj"], Image.Image):
        return payload["image_obj"], "payload_obj"

    # 2. GridFS image ID
    image_id = payload.get("image_id") or attachment.get("image_id")
    if image_id:
        img = await fetch_image_from_gridfs(db, image_id)
        if img:
            return img, str(image_id)

    # 3. CDN or Web URL
    url = payload.get("url") or attachment.get("url") or payload.get("file_url")
    if url:
        img = await fetch_image_from_url(url)
        if img:
            return img, url

    return None, None


async def match_image_to_posts(
    db,
    query_image: Image.Image,
    workspace_id: str,
    max_hamming: int = MAX_HAMMING_MATCH,
) -> tuple[dict | None, float, str, bool, list[str]]:
    """Matches an incoming query image against all indexed published posts for a workspace.
    
    Returns:
        (best_post, confidence, match_method, is_ambiguous, candidate_titles)
    """
    query_fp = compute_image_fingerprint(query_image)
    query_dhash = query_fp["dhash"]
    
    # Find all published posts in this workspace
    cursor = db.social_posts.find({
        "workspace_id": workspace_id,
        "post_status": "published",
    })
    
    scored_candidates = []
    
    async for post in cursor:
        post_fp = post.get("image_fingerprint")
        post_dhash = (post_fp.get("dhash") if post_fp else None) or post.get("image_hash")
        
        # If post does not have hash but has media_reference, try on-demand fetch & cache
        if not post_dhash and post.get("media_reference"):
            try:
                ref = str(post["media_reference"])
                ref_img = None
                if ref.startswith("http"):
                    ref_img = await fetch_image_from_url(ref)
                else:
                    ref_img = await fetch_image_from_gridfs(db, ref)
                if ref_img:
                    post_fp = compute_image_fingerprint(ref_img)
                    post_dhash = post_fp["dhash"]
                    # Cache back to post
                    await db.social_posts.update_one(
                        {"_id": post["_id"]},
                        {"$set": {"image_fingerprint": post_fp, "image_hash": post_dhash}},
                    )
            except Exception:
                pass
                
        if not post_dhash:
            continue
            
        h_dist = hamming_distance(query_dhash, post_dhash)
        if h_dist <= max_hamming:
            score = visual_similarity_score(query_fp, post_fp or {"dhash": post_dhash})
            scored_candidates.append((h_dist, score, post))
            
    if not scored_candidates:
        return None, 0.0, "none", False, []
        
    # Sort by minimum hamming distance, then maximum similarity score
    scored_candidates.sort(key=lambda item: (item[0], -item[1]))
    
    best_dist, best_score, best_post = scored_candidates[0]
    
    # Check for ambiguity: multiple different posts within AMBIGUITY_DELTA bits
    ambiguous_posts = []
    best_pid = str(best_post["_id"])
    candidate_titles = [best_post.get("title") or best_post.get("subject") or "This post"]
    
    for dist, score, p in scored_candidates[1:]:
        if str(p["_id"]) != best_pid and dist <= best_dist + AMBIGUITY_DELTA:
            t = p.get("title") or p.get("subject") or "Another post"
            if t not in candidate_titles:
                candidate_titles.append(t)
                ambiguous_posts.append(p)
                
    is_ambiguous = len(ambiguous_posts) > 0
    method = "image_hash" if best_dist <= 6 else "visual_similarity"
    
    return best_post, best_score, method, is_ambiguous, candidate_titles[:3]

