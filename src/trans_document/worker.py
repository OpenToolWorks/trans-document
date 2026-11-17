"""BabelDOC imports and credentials stay in the translation process."""

import asyncio
import logging
from pathlib import Path


def translate_worker(request, output_dir, connection):
    # Provider/backend log messages may include document text or credentials.
    # The UI receives only projected progress and known error categories.
    logging.disable(logging.CRITICAL)
    translator = None
    try:
        from babeldoc.format.pdf.high_level import async_translate
        from babeldoc.format.pdf.translation_config import (
            TranslationConfig,
            WatermarkOutputMode,
        )
        from babeldoc.translator.translator import (
            OpenAITranslator,
            set_translate_rate_limiter,
        )

        set_translate_rate_limiter(2)
        translator = OpenAITranslator(
            request.lang_in, request.lang_out, request.model.strip(),
            base_url=request.base_url.strip(), api_key=request.api_key.strip(),
            enable_json_mode_if_requested=False,
        )
        # BabelDOC's upstream cache omits endpoint identity by default.
        translator.add_cache_impact_parameters("base_url", request.base_url.rstrip("/"))
        # BabelDOC can fall back to source text after provider failures. Validate
        # credentials first so an unavailable API cannot look like success.
        translator.translate("Hello", ignore_cache=True)
        config = TranslationConfig(
            translator=translator, input_file=Path(request.pdf_path),
            lang_in=request.lang_in, lang_out=request.lang_out,
            doc_layout_model=None, output_dir=Path(output_dir),
            watermark_output_mode=WatermarkOutputMode.NoWatermark,
            use_rich_pbar=False, auto_extract_glossary=False,
            qps=2, pool_max_workers=2, report_interval=0.5,
            pages=f"1-{request.preview_pages}" if request.preview_pages else None,
            only_include_translated_page=bool(request.preview_pages),
        )

        async def run():
            async for event in async_translate(config):
                event_type = event.get("type")
                if event_type == "finish":
                    result = event["translate_result"]
                    connection.send({"type": "finish", "mono": str(result.mono_pdf_path),
                                     "dual": str(result.dual_pdf_path)})
                    return
                if event_type == "error":
                    connection.send({"type": "error", "code": _error_code(event.get("error"))})
                    return
                if event_type in {"progress_start", "progress_update", "progress_end"}:
                    connection.send({"type": "progress", "stage": event.get("stage", ""),
                                     "percent": event.get("overall_progress", 0)})

        asyncio.run(run())
    except Exception as error:
        connection.send({"type": "error", "code": _error_code(error)})
    finally:
        if translator is not None:
            translator.client.close()
        connection.close()


def check_connection(base_url, model, api_key):
    import httpx
    import openai

    client = None
    try:
        client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=httpx.Client(timeout=10, follow_redirects=False),
            timeout=10,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello"}],
        )
        return "ok" if response.choices[0].message.content else "backend"
    except Exception as error:
        return _error_code(error)
    finally:
        if client is not None:
            client.close()


def _error_code(error):
    import openai

    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "authentication"
    if isinstance(error, openai.RateLimitError):
        return "quota"
    if isinstance(error, (openai.APIConnectionError, openai.APITimeoutError)):
        return "connection"
    if isinstance(error, openai.BadRequestError):
        return "backend"
    if error and type(error).__name__ in {"ScannedPDFError", "ExtractTextError", "FileDataError"}:
        return "pdf"
    return "backend"
