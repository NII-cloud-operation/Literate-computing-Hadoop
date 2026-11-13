"""Capture browser traces and full-resolution per-page videos."""
from pathlib import Path


def recorded_context(browser, videos, *, viewport=None):
    size = viewport or {'width': 1280, 'height': 720}
    return browser.new_context(
        ignore_https_errors=True, viewport=size,
        record_video_dir=str(videos), record_video_size=size,
    )


def finish_recording(context, trace, videos):
    try:
        context.tracing.stop(path=str(trace))
    finally:
        # Closing the context finalizes videos, including pages already closed.
        context.close()
    recordings = sorted(Path(videos).glob('*.webm'))
    assert recordings, f'No browser video recorded in {videos}'
    for path in recordings:
        assert path.stat().st_size > 0, f'Empty browser video: {path}'
        print(f'BROWSER VIDEO: {path} ({path.stat().st_size} bytes)', flush=True)
