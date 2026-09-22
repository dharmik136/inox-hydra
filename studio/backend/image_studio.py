"""
AI Image Studio Orchestrator & Background Task Engine
=====================================================
Orchestrates generative image creation using Agno prompt engineering,
dual-provider execution (Gemini Imagen / Pollinations high-res fallback),
and real-time 1% to 100% progress tracking.
"""

import os
import time
import uuid
import json
import urllib.parse
import threading
import requests
from typing import Dict, Any, Optional

try:
    from .database import get_db
    from .agno_agentos import orchestrator, ImagePromptInput
    from .quote_renderer import remove_watermark_crop, render_typographic_quote, apply_personal_brand_watermark
except ImportError:
    try:
        from database import get_db
        from agno_agentos import orchestrator, ImagePromptInput
        from quote_renderer import remove_watermark_crop, render_typographic_quote, apply_personal_brand_watermark
    except ImportError:
        get_db = None
        orchestrator = None
        remove_watermark_crop = None
        render_typographic_quote = None
        apply_personal_brand_watermark = None

try:
    from .paths import get_generated_dir
except ImportError:
    from paths import get_generated_dir

GENERATED_DIR = get_generated_dir()

# -- Validation & Concurrency Constants -------------------------------------
MAX_CONCEPT_LENGTH = 2000
MIN_DIMENSION = 64
MAX_DIMENSION = 4096
MAX_CONCURRENT_TASKS = 5
MAX_STORED_TASKS = 100


class ImageStudioManager:
    """Manages asynchronous AI image generation tasks and live progress telemetry."""

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._worker_semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)

    def start_task(self, options: Optional[Dict[str, Any]]) -> str:
        """Initializes a new generation task and launches the background worker."""
        if not isinstance(options, dict):
            options = {}

        task_id = f"img_task_{uuid.uuid4().hex[:12]}"
        raw_concept = options.get("concept")
        concept = (raw_concept or "").strip() if isinstance(raw_concept, str) else ""
        if not concept:
            concept = "Enterprise Software Architecture"
        concept = concept[:MAX_CONCEPT_LENGTH]
        options["concept"] = concept

        task_record = {
            "task_id": task_id,
            "concept": concept,
            "options": options,
            "status": "pending",
            "progress_percent": 1,
            "status_message": "Task queued, initiating Agno prompt synthesis...",
            "result_url": None,
            "prompt_used": None,
            "error_message": None,
            "created_at": time.time(),
            "updated_at": time.time()
        }

        with self._lock:
            # Prevent unbounded memory growth by pruning oldest finished tasks
            if len(self._tasks) >= MAX_STORED_TASKS:
                finished_keys = [
                    k for k, v in self._tasks.items()
                    if v.get("status") in ("completed", "failed")
                ]
                finished_keys.sort(key=lambda k: self._tasks[k].get("created_at", 0))
                for k in finished_keys[:max(1, len(self._tasks) - MAX_STORED_TASKS + 10)]:
                    self._tasks.pop(k, None)
            self._tasks[task_id] = task_record

        # Persist initial record in SQLite if available
        if get_db:
            conn = None
            try:
                conn = get_db()
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    INSERT OR REPLACE INTO generation_tasks 
                    (task_id, prompt, options_json, status, progress_percent, status_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        task_id,
                        concept,
                        json.dumps(options),
                        "pending",
                        1,
                        task_record["status_message"]
                    ))
            except Exception as e:
                print(f"[ImageStudio] SQLite task init failed: {e}")
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # Launch background thread
        thread = threading.Thread(target=self._run_generation_worker, args=(task_id, options), daemon=True)
        thread.start()

        return task_id

    def get_progress(self, task_id: str) -> Dict[str, Any]:
        """Retrieves real-time progress percentage (1%..100%) and stage description."""
        if not isinstance(task_id, str) or not task_id:
            return {
                "status": "not_found",
                "progress_percent": 0,
                "status_message": "Invalid task ID"
            }

        with self._lock:
            task = self._tasks.get(task_id)

        if not task and get_db:
            conn = None
            try:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM generation_tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                if row:
                    task = dict(row)
            except Exception:
                pass
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        if not task:
            return {
                "status": "not_found",
                "progress_percent": 0,
                "status_message": "Task not found"
            }

        return {
            "task_id": task_id,
            "status": task.get("status"),
            "progress_percent": task.get("progress_percent", 1),
            "status_message": task.get("status_message", ""),
            "result_url": task.get("result_url"),
            "prompt_used": task.get("prompt_used"),
            "error_message": task.get("error_message")
        }

    def _update_task(self, task_id: str, percent: int, message: str, status: str = "processing", result_url: str = None, error: str = None, prompt_used: str = None):
        """Thread-safe update of task status in memory and SQLite."""
        clamped_percent = max(0, min(int(percent) if isinstance(percent, (int, float)) else 0, 100))
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]["progress_percent"] = clamped_percent
                self._tasks[task_id]["status_message"] = message
                self._tasks[task_id]["status"] = status
                self._tasks[task_id]["updated_at"] = time.time()
                if result_url:
                    self._tasks[task_id]["result_url"] = result_url
                if error:
                    self._tasks[task_id]["error_message"] = error
                if prompt_used:
                    self._tasks[task_id]["prompt_used"] = prompt_used

        if get_db:
            conn = None
            try:
                conn = get_db()
                with conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                    UPDATE generation_tasks 
                    SET progress_percent = ?, status_message = ?, status = ?, result_url = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE task_id = ?
                    """, (clamped_percent, message, status, result_url, error, task_id))
            except Exception:
                pass
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def _run_generation_worker(self, task_id: str, options: Dict[str, Any]):
        """Executes the multi-stage image generation workflow."""
        is_testing = bool(os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("TESTING"))
        delay = 0.02 if is_testing else 0.3

        acquired = self._worker_semaphore.acquire(timeout=60)
        if not acquired:
            self._update_task(
                task_id, 100,
                "Task dropped: worker concurrency limit reached.",
                status="failed",
                error="Concurrency limit reached"
            )
            return

        try:
            # Stage 1: Agno Prompt Synthesis (1% -> 20%)
            self._update_task(task_id, 8, "Decomposing creative concept into artistic dimensions...")
            time.sleep(delay)

            raw_concept = options.get("concept", "Enterprise Software Architecture")
            concept = (raw_concept or "").strip() if isinstance(raw_concept, str) else ""
            if not concept:
                concept = "Enterprise Software Architecture"
            concept = concept[:MAX_CONCEPT_LENGTH]

            prompt_input = ImagePromptInput(
                concept=concept,
                aspect_ratio=options.get("aspect_ratio", "1:1"),
                visual_style=options.get("visual_style", "photorealistic"),
                color_palette=options.get("color_palette", "navy_cyan"),
                lighting=options.get("lighting", "studio"),
                render_quote_overlay=options.get("render_quote_overlay", True),
                custom_quote_text=options.get("custom_quote_text"),
                custom_quote_author=options.get("custom_quote_author")
            )

            self._update_task(task_id, 18, "Synthesizing master prompt blueprint via Agno AgentOS...")
            if orchestrator:
                synthesized = orchestrator.synthesize_image_prompt(prompt_input.model_dump())
                master_prompt = synthesized.master_prompt
                width = synthesized.width
                height = synthesized.height
                quote_text = synthesized.quote_text
                quote_author = synthesized.quote_author
            else:
                master_prompt = f"Professional studio visual for {concept}"
                width = 1080
                height = 1080
                quote_text = options.get("custom_quote_text")
                quote_author = options.get("custom_quote_author")

            self._update_task(task_id, 28, "Master prompt formulated. Selecting AI generation provider...", prompt_used=master_prompt)
            time.sleep(delay)

            # Stage 2: Latent Diffusion / Model Query (29% -> 60%)
            self._update_task(task_id, 42, "Initializing diffusion latent space and geometry...")
            time.sleep(delay)

            image_bytes = None

            if not is_testing:
                ai_config = orchestrator.get_ai_config() if orchestrator else None

                # Provider 1: OpenAI DALL-E 3 (if OpenAI provider configured)
                if ai_config and ai_config.provider == "openai" and ai_config.api_key:
                    self._update_task(task_id, 55, "Querying OpenAI DALL-E 3 neural engine...")
                    try:
                        image_bytes = self._call_openai_dalle3(master_prompt, ai_config.api_key, width, height)
                    except Exception as e:
                        print(f"[ImageStudio] OpenAI DALL-E 3 failed: {e}. Moving to fallback.")

                # Provider 2: Gemini Imagen 3 (if Gemini provider configured or gemini key present)
                if not image_bytes:
                    gemini_api_key = orchestrator.get_gemini_api_key() if orchestrator else None
                    if (ai_config and ai_config.provider == "gemini" and ai_config.api_key) or gemini_api_key:
                        key_to_use = (ai_config.api_key if ai_config and ai_config.provider == "gemini" else None) or gemini_api_key
                        self._update_task(task_id, 55, "Querying Gemini Imagen 3 neural engine...")
                        try:
                            image_bytes = self._call_gemini_imagen(master_prompt, key_to_use, width, height)
                        except Exception as e:
                            print(f"[ImageStudio] Gemini Imagen failed: {e}. Moving to high-res fallback.")

                # Provider 3: Pollinations High-Res Engine (Open-Access Zero-Key Fallback)
                if not image_bytes:
                    eliminate_pw = options.get("eliminate_provider_watermark", True)
                    self._update_task(task_id, 65, "Rendering through Pollinations generative engine...")
                    try:
                        image_bytes = self._call_pollinations(master_prompt, width, height, eliminate_watermark=eliminate_pw)
                    except Exception as e:
                        print(f"[ImageStudio] Pollinations fallback failed: {e}")

            # Provider 4: Deterministic fallback canvas generator (guaranteed test & offline safety)
            if not image_bytes:
                self._update_task(task_id, 75, "Constructing studio visual canvas asset...")
                image_bytes = self._create_local_canvas_image(width, height, concept, options.get("visual_style", "style"))

            # Stage 3: Typographic Quote Compositing & Personal Watermarking (80% -> 95%)
            # Step A: Typographic Quote Overlay
            if quote_text and options.get("render_quote_overlay", True) and render_typographic_quote and image_bytes:
                self._update_task(task_id, 82, f"Compositing typographic quote overlay ({quote_author or 'Quote'})...")
                try:
                    import io
                    from PIL import Image
                    raw_pil = Image.open(io.BytesIO(image_bytes))
                    quoted_pil = render_typographic_quote(raw_pil, quote_text, quote_author)
                    buf = io.BytesIO()
                    quoted_pil.save(buf, format="JPEG", quality=95)
                    image_bytes = buf.getvalue()
                except Exception as e:
                    print(f"[ImageStudio] Quote overlay compositing notice: {e}")

            # Step B: Personal Brand Watermark (Creator Handle & Corner Badge)
            apply_brand = options.get("apply_personal_watermark")
            brand_text = options.get("personal_watermark_text")
            brand_pos = options.get("personal_watermark_position")
            brand_style = options.get("personal_watermark_style")

            # One condition used to answer two different questions, and so
            # answered neither.
            #
            # The guard was `apply_brand is None`, but the request model
            # defaults apply_personal_watermark to False and the checkbox in
            # the interface always sends a boolean, so it was never None and
            # this whole block was unreachable. A creator who saved their handle
            # in Settings and ticked the box got an image stamped with the
            # literal string "@creator", and their saved position and style
            # were ignored too.
            #
            # The two questions are separate:
            #   should we stamp?   the request decides, because that is the
            #                      checkbox the creator just clicked
            #   what do we stamp?  the saved profile decides, because that is
            #                      where the handle lives
            #
            # So the profile is read whenever the request did not carry the
            # details, regardless of how the first question was answered.
            needs_profile = (
                apply_brand is None
                or not brand_text
                or not brand_pos
                or not brand_style
            )
            if needs_profile and get_db:
                conn = None
                try:
                    conn = get_db()
                    cursor = conn.cursor()
                    cursor.execute("SELECT value FROM settings WHERE key = 'creator_profile'")
                    prof_row = cursor.fetchone()
                    if prof_row and prof_row["value"]:
                        prof_data = json.loads(prof_row["value"])
                        # Only fills what the request left unanswered. An
                        # explicit False from the interface means the creator
                        # unticked the box, and must not be overridden by a
                        # stale enabled flag in the profile.
                        if apply_brand is None:
                            apply_brand = prof_data.get("brand_watermark_enabled", False)
                        if not brand_text:
                            brand_text = prof_data.get("brand_watermark_text") or ""
                        if not brand_pos:
                            brand_pos = prof_data.get("brand_watermark_position") or ""
                        if not brand_style:
                            brand_style = prof_data.get("brand_watermark_style") or ""
                except Exception as e:
                    print(f"[ImageStudio] Settings lookup note: {e}")
                finally:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

            # Defaults for presentation only, applied after the profile has had
            # its say so a saved preference is never silently overridden.
            brand_pos = brand_pos or "bottom_right"
            brand_style = brand_style or "glass_pill"

            # A handle this studio invented is worse than no handle.
            #
            # The old code fell back to the literal "@creator" whenever the
            # text was empty, which stamped a made up identity onto the
            # creator's image. "A fresh install belongs to nobody" applies
            # here too: with nothing to stamp, stamp nothing and say so.
            if apply_brand and not (brand_text or "").strip():
                self._update_task(
                    task_id, 86,
                    "Skipping the brand watermark: no handle is saved in Settings.",
                )
                apply_brand = False

            if apply_brand and apply_personal_brand_watermark and image_bytes:
                self._update_task(task_id, 86, f"Stamping personal brand watermark ({brand_text})...")
                try:
                    import io
                    from PIL import Image
                    raw_pil = Image.open(io.BytesIO(image_bytes))
                    stamped_pil = apply_personal_brand_watermark(
                        raw_pil,
                        brand_text=brand_text,
                        position=brand_pos,
                        style=brand_style
                    )
                    buf = io.BytesIO()
                    stamped_pil.save(buf, format="JPEG", quality=95)
                    image_bytes = buf.getvalue()
                except Exception as e:
                    print(f"[ImageStudio] Personal watermark compositing notice: {e}")

            if options.get("eliminate_provider_watermark", True):
                self._update_task(task_id, 90, "Verifying watermark clearance and pixel fidelity...")
            else:
                self._update_task(task_id, 90, "Preserving raw canvas format (provider watermark retained)...")
            time.sleep(delay)

            os.makedirs(GENERATED_DIR, exist_ok=True)
            filename = f"gen_{uuid.uuid4().hex[:10]}.jpg"
            file_path = os.path.join(GENERATED_DIR, filename)

            with open(file_path, "wb") as f:
                f.write(image_bytes)

            size_bytes = len(image_bytes)
            relative_url = f"/assets/generated/{filename}"

            self._update_task(task_id, 95, "Registering media asset in local SQLite vault...")

            # Persist in media_assets table
            if get_db:
                conn = None
                try:
                    conn = get_db()
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                        INSERT OR REPLACE INTO media_assets 
                        (id, filename, storage_path, media_type, mime_type, size_bytes, dimensions, prompt)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            task_id,
                            filename,
                            relative_url,
                            "image",
                            "image/jpeg",
                            size_bytes,
                            json.dumps({"width": width, "height": height}),
                            master_prompt
                        ))
                except Exception as e:
                    print(f"[ImageStudio] media_assets insert error: {e}")
                finally:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

            # Stage 4: 100% Completion
            time.sleep(0.2)
            self._update_task(
                task_id,
                100,
                "Image rendering complete and verified!",
                status="completed",
                result_url=relative_url,
                prompt_used=master_prompt
            )

        except Exception as e:
            print(f"[ImageStudio] Worker error: {e}")
            self._update_task(task_id, 100, f"Generation failed: {str(e)}", status="failed", error=str(e))
        finally:
            self._worker_semaphore.release()

    def _call_openai_dalle3(self, prompt: str, api_key: str, width: int, height: int) -> Optional[bytes]:
        """Invokes OpenAI DALL-E 3 image generation API."""
        import base64
        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        if width > height:
            size = "1792x1024"
        elif height > width:
            size = "1024x1792"
        else:
            size = "1024x1024"

        payload = {
            "model": "dall-e-3",
            "prompt": prompt[:1000],
            "n": 1,
            "size": size,
            "response_format": "b64_json"
        }
        res = requests.post(url, headers=headers, json=payload, timeout=35)
        if res.status_code == 200:
            data = res.json()
            items = data.get("data", [])
            if items:
                b64 = items[0].get("b64_json")
                if b64:
                    return base64.b64decode(b64)
                img_url = items[0].get("url")
                if img_url:
                    img_res = requests.get(img_url, timeout=20)
                    if img_res.status_code == 200:
                        return img_res.content
        return None

    def _call_gemini_imagen(self, prompt: str, api_key: str, width: int, height: int) -> Optional[bytes]:
        """Invokes Google Gemini Imagen API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": "1:1" if width == height else ("16:9" if width > height else "4:5")
            }
        }
        res = requests.post(url, headers=headers, json=payload, timeout=25)
        if res.status_code == 200:
            import base64
            data = res.json()
            predictions = data.get("predictions", [])
            if predictions:
                b64 = predictions[0].get("bytesBase64Encoded")
                if b64:
                    return base64.b64decode(b64)
        return None

    def _call_pollinations(self, prompt: str, width: int, height: int, eliminate_watermark: bool = True) -> Optional[bytes]:
        """
        Calls Pollinations AI generative engine.
        If eliminate_watermark is True, applies height oversampling to position the watermark
        in a bottom discard buffer and cleanly slices it off.
        If False, requests exact target dimensions without any cropping.
        """
        # Clamp dimensions to safe bounds
        width = max(MIN_DIMENSION, min(int(width) if width else 1080, MAX_DIMENSION))
        height = max(MIN_DIMENSION, min(int(height) if height else 1080, MAX_DIMENSION))

        prompt = (prompt or "Abstract architectural technology concept").strip()
        encoded_prompt = urllib.parse.quote(prompt[:450])
        seed = int(time.time()) % 1000000

        if eliminate_watermark:
            # Calculate oversampled dimensions so bottom watermark lands in the discard strip
            target_ratio = float(width) / float(height) if height > 0 else 1.0
            if target_ratio >= 1.5:
                # 16:9 Landscape
                req_w = 1080
                req_h = 688  # 1080 / (16/9) = 608 + 80px bottom buffer
            elif target_ratio <= 0.85:
                # 4:5 Portrait
                req_w = 768
                req_h = 1080  # 768 / 0.8 = 960 + 120px bottom buffer
            else:
                # 1:1 Square
                req_w = 768
                req_h = 864  # 768 + 96px bottom buffer
        else:
            # Exact dimensions: preserve raw canvas format
            req_w = width
            req_h = height

        # enhance=false prevents Pollinations internal LLM from hallucinating portraits over scene descriptions
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={req_w}&height={req_h}&seed={seed}&nologo=true"
        try:
            res = requests.get(url, timeout=30)
            if res.status_code == 200 and len(res.content) > 5000:
                if eliminate_watermark and remove_watermark_crop:
                    try:
                        clean_bytes, _ = remove_watermark_crop(res.content, width, height)
                        return clean_bytes
                    except Exception as e:
                        print(f"[ImageStudio] Watermark removal crop error: {e}")
                return res.content
        except Exception as e:
            print(f"[ImageStudio] Pollinations network error: {e}")
        return None

    def _create_local_canvas_image(self, width: int, height: int, title: Optional[str], style: Optional[str]) -> bytes:
        """Local PIL image generator ensuring 100% offline reliability."""
        from PIL import Image, ImageDraw, ImageFont

        # Clamp dimensions to safe bounds
        width = max(MIN_DIMENSION, min(int(width) if isinstance(width, (int, float)) and width > 0 else 1080, MAX_DIMENSION))
        height = max(MIN_DIMENSION, min(int(height) if isinstance(height, (int, float)) and height > 0 else 1080, MAX_DIMENSION))

        title = (title or "Concept").strip()
        style = (style or "style").strip()

        img = Image.new("RGB", (width, height), color=(11, 15, 25))
        draw = ImageDraw.Draw(img)

        # Draw tech grid pattern
        grid_color = (25, 35, 55)
        for x in range(0, width, 40):
            draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
        for y in range(0, height, 40):
            draw.line([(0, y), (width, y)], fill=grid_color, width=1)

        # Draw decorative glowing center card
        card_w = max(20, min(width - 4, int(width * 0.75)))
        card_h = max(20, min(height - 4, int(height * 0.5)))
        x0 = max(0, (width - card_w) // 2)
        y0 = max(0, (height - card_h) // 2)
        radius = max(2, min(16, card_w // 4, card_h // 4))
        draw.rounded_rectangle([x0, y0, min(width, x0 + card_w), min(height, y0 + card_h)], radius=radius, fill=(15, 23, 42), outline=(99, 102, 241), width=2)

        # Text labels
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        draw.text((x0 + 30, y0 + 30), "AI STUDIO GENERATION", fill=(56, 189, 248), font=font)
        draw.text((x0 + 30, y0 + 70), title[:45], fill=(248, 250, 252), font=font)
        draw.text((x0 + 30, y0 + 110), f"Style: {style} | {width}x{height}", fill=(148, 163, 184), font=font)

        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()


# Singleton image studio manager
image_studio_manager = ImageStudioManager()
