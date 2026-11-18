"""Capture browser traces and full-resolution per-page videos."""
import json
from pathlib import Path
import time


def recorded_context(browser, videos, *, viewport=None):
    size = viewport or {'width': 1280, 'height': 720}
    return browser.new_context(
        ignore_https_errors=True, viewport=size, locale='ja-JP',
        record_video_dir=str(videos), record_video_size=size,
    )


class NotebookVideos:
    def __init__(self, context, results):
        self.context = context
        self.results = Path(results)
        self.recordings = []
        self.segments = []
        self.active = None

    def new_page(self, notebook, document):
        page = self.context.new_page()
        self.recordings.append(dict(page=page, notebook=notebook, document=document,
                                    started=time.monotonic()))
        self.activate(page)
        return page

    def end_segment(self):
        if self.active is not None:
            recording = self.recordings[self.active['recording']]
            self.active['end'] = time.monotonic() - recording['started']
            self.active = None

    def activate(self, page):
        self.end_segment()
        index = next(i for i, item in enumerate(self.recordings) if item['page'] is page)
        self.active = dict(recording=index, start=time.monotonic() - self.recordings[index]['started'])
        self.segments.append(self.active)
        page.bring_to_front()

    def close_page(self, page, resume=None):
        self.end_segment()
        page.close()
        if resume is not None:
            self.activate(resume)

    def finish(self):
        self.end_segment()
        try:
            self.context.tracing.stop(path=str(self.results / 'browser-trace.zip'))
        finally:
            self.context.close()
        recordings = []
        for index, item in enumerate(self.recordings):
            key = item['notebook'].split('_', 1)[0]
            path = self.results / 'videos' / key / f'{index:02d}.webm'
            path.parent.mkdir(parents=True, exist_ok=True)
            original = item['page'].video.path()
            item['page'].video.save_as(str(path))
            original.unlink()
            assert path.stat().st_size > 0, path
            recordings.append(dict(notebook=item['notebook'], document=item['document'],
                                   path=str(path.relative_to(self.results))))
        (self.results / 'video-manifest.json').write_text(
            json.dumps(dict(recordings=recordings, segments=self.segments), indent=2) + '\n')
