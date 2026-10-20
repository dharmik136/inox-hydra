"""
AI Image Studio Orchestrator & Background Task Engine
=====================================================
Orchestrates generative image creation using Agno prompt engineering, the
image provider the creator chose (image_providers.py), and real-time 1% to
100% progress tracking.

A generation either produces the provider's image or fails with the reason.
It never stands in a drawn placeholder for a failed or refused request, and
nothing reaches the media library unless the provider made it (BE-06).
"""

import os
import time
import io
import uuid
import json
import contextvars
import threading

try:  # the shared egress chokepoint
    from . import egress as _egress
except ImportError:
    import egress as _egress
from typing import Dict, Any, Optional

try:
    from .database import get_db
    from .agno_agentos import orchestrator, ImagePromptInput
    from .quote_renderer import render_typographic_quote, apply_personal_brand_watermark, TextNotDrawn
    from . import image_providers
except ImportError:
    try:
        from database import get_db
        from agno_agentos import orchestrator, ImagePromptInput
        from quote_renderer import render_typographic_quote, apply_personal_brand_watermark, TextNotDrawn
        import image_providers
    except ImportError:
        get_db = None
        orchestrator = None
        render_typographic_quote = None
        apply_personal_brand_watermark = None
        TextNotDrawn = Exception
        image_providers = None

try:
    from .paths import get_generated_dir
except ImportError:
    from paths import get_generated_dir

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

    def _evict_locked(self):
        """
        Keeps the in-memory task table under its cap. Caller holds the lock.

        Finished tasks go first, oldest first, because they have already been
        reported. If that is not enough, live tasks go too, oldest first.

        Only pruning finished tasks could not bound anything. The semaphore
        limits how many generations run at once, not how many are submitted,
        so a burst sits here as "processing" with nothing eligible to evict
        and the dict grows without limit.

        Evicting a live task is safe because get_progress falls back to the
        generation_tasks table when the in-memory record is gone. This dict is
        a cache, not the record.
        """
        if len(self._tasks) < MAX_STORED_TASKS:
            return

        def _age(key):
            return self._tasks[key].get("created_at", 0)

        target = MAX_STORED_TASKS - 10

        finished = sorted(
            (k for k, v in self._tasks.items()
             if v.get("status") in ("completed", "failed")),
            key=_age,
        )
        for key in finished:
            if len(self._tasks) <= target:
                break
            self._tasks.pop(key, None)

        if len(self._tasks) > target:
            for key in sorted(self._tasks, key=_age):
                if len(self._tasks) <= target:
                    break
                self._tasks.pop(key, None)

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
            "notice": None,
            "created_at": time.time(),
            "updated_at": time.time()
        }

        with self._lock:
            self._evict_locked()
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

        # Launch background thread. It runs in a copy of this request's
        # context, so it writes to the creator profile the request was for.
        context = contextvars.copy_context()
        thread = threading.Thread(
            target=context.run, args=(self._run_generation_worker, task_id, options), daemon=True
        )
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
            # Snapshot, not a reference.
            #
            # The reference was taken under the lock and then six fields were
            # read outside it, while a worker thread mutated the same dict. A
            # poller could therefore see status "completed" from after the
            # update and result_url None from before it, and render a finished
            # image with no image.
            if task is not None:
                task = dict(task)

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
            "error_message": task.get("error_message"),
            # What the creator should know about a finished image, such as a
            # quote that was not drawn. Also in status_message, which is kept.
            "notice": task.get("notice"),
        }

    def _update_task(self, task_id: str, percent: int, message: str, status: str = "processing", result_url: str = None, error: str = None, prompt_used: str = None, notice: str = None):
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
                if notice:
                    self._tasks[task_id]["notice"] = notice

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

    def _fail(self, task_id: str, reason: str):
        """Ends a task as failed, with the reason in words. Nothing is saved."""
        reason = _egress.redact(reason)
        print(f"[ImageStudio] Generation failed: {reason}")
        self._update_task(task_id, 100, f"Generation failed: {reason}", status="failed", error=reason)

    def _run_generation_worker(self, task_id: str, options: Dict[str, Any]):
        """Executes the multi-stage image generation workflow."""
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
            # Read first: a provider that is off or missing its key fails here,
            # before the description goes to an AI provider to be worked on.
            provider = image_providers.current_config()
            not_ready = provider.not_ready()
            if not_ready:
                self._fail(task_id, not_ready)
                return

            # Stage 1: the prompt (1% -> 28%)
            self._update_task(task_id, 8, "Reading your description...")

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

            self._update_task(task_id, 18, "Writing the image prompt...")
            negative_prompt = ""
            if orchestrator:
                synthesized = orchestrator.synthesize_image_prompt(prompt_input.model_dump())
                master_prompt = synthesized.master_prompt
                negative_prompt = synthesized.negative_prompt
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

            self._update_task(task_id, 28, "Prompt ready.", prompt_used=master_prompt)

            # Stage 2: the chosen provider, and only it (29% -> 75%)
            #
            # This used to try OpenAI, then Gemini, then Pollinations, catch
            # every failure and refusal, and finally draw a grey grid labelled
            # AI STUDIO GENERATION that was saved as generated media and
            # reported "complete and verified" (BE-06). A failure now ends the
            # task as failed with the provider's reason, and nothing is saved.
            self._update_task(task_id, 40, f"Sending the prompt to {provider.name}...")
            try:
                image_bytes = image_providers.generate(
                    provider, master_prompt, negative_prompt, width, height,
                    eliminate_watermark=options.get("eliminate_provider_watermark", True),
                )
            except image_providers.ImageProviderError as failure:
                self._fail(task_id, str(failure))
                return

            # Every provider's image at the size the prompt asked for, as JPEG,
            # whatever size and format it came back in.
            image_bytes = _fit_jpeg(image_bytes, width, height)
            self._update_task(task_id, 75, f"Image received from {provider.name}.")

            notices = []

            # Stage 3: Typographic Quote Compositing & Personal Watermarking (80% -> 95%)
            # Step A: Typographic Quote Overlay
            if quote_text and options.get("render_quote_overlay", True) and render_typographic_quote and image_bytes:
                self._update_task(task_id, 82, "Drawing the quote...")
                try:
                    from PIL import Image
                    raw_pil = Image.open(io.BytesIO(image_bytes))
                    quoted_pil = render_typographic_quote(raw_pil, quote_text, quote_author, notes=notices)
                    buf = io.BytesIO()
                    quoted_pil.save(buf, format="JPEG", quality=95)
                    image_bytes = buf.getvalue()
                except TextNotDrawn as why:
                    notices.append(f"The quote was not drawn: {why}.")
                except Exception as e:
                    notices.append(f"The quote was not drawn: {_egress.redact(e)}.")

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
                    from PIL import Image
                    raw_pil = Image.open(io.BytesIO(image_bytes))
                    stamped_pil = apply_personal_brand_watermark(
                        raw_pil,
                        brand_text=brand_text,
                        position=brand_pos,
                        style=brand_style,
                        notes=notices,
                    )
                    buf = io.BytesIO()
                    stamped_pil.save(buf, format="JPEG", quality=95)
                    image_bytes = buf.getvalue()
                except TextNotDrawn as why:
                    notices.append(f"The watermark was not drawn: {why}.")
                except Exception as e:
                    notices.append(f"The watermark was not drawn: {_egress.redact(e)}.")

            generated_dir = get_generated_dir()
            filename = f"gen_{uuid.uuid4().hex[:10]}.jpg"
            file_path = os.path.join(generated_dir, filename)

            with open(file_path, "wb") as f:
                f.write(image_bytes)

            size_bytes = len(image_bytes)
            relative_url = f"/assets/generated/{filename}"

            self._update_task(task_id, 95, "Saving to the media library...")

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
                    # A file nobody can find in the library is not a success.
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                    self._fail(task_id, f"The image could not be added to the media library: {e}")
                    return
                finally:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

            # Stage 4: 100% Completion. Says what happened, and nothing it
            # did not check.
            notice = " ".join(notices) or None
            self._update_task(
                task_id,
                100,
                f"Image ready from {provider.name}. It is in the media library."
                + (f" {notice}" if notice else ""),
                status="completed",
                result_url=relative_url,
                prompt_used=master_prompt,
                notice=notice,
            )

        except Exception as e:
            # Redacted on the way to the log and to the progress endpoint.
            self._fail(task_id, _plain_failure(e))
        finally:
            self._worker_semaphore.release()


def _plain_failure(error: Exception) -> str:
    """A sentence for an unexpected failure, without a library's internals."""
    text = _egress.redact(error)
    if "validation error" in text or "pydantic" in text:
        return "The description could not be used. Write at least three characters."
    return text


def _fit_jpeg(data: bytes, width: int, height: int) -> bytes:
    """
    The image at exactly width x height, as JPEG.

    Providers answer in their own sizes (1024x1024, 1536x1024...) and
    formats (PNG, WebP). Scaled to cover and centre-cropped, so nothing is
    stretched, then saved as the .jpg the library names it.
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGB")
    if image.size != (width, height):
        image = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# Singleton image studio manager
image_studio_manager = ImageStudioManager()
