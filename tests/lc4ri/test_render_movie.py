"""Check chronological assembly without invoking the video codec."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import render_movie


class MovieOrderTest(unittest.TestCase):
    def test_returning_to_a_notebook_keeps_execution_order(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            recordings = [
                dict(notebook='T12d_Spark.ipynb', path='before.webm'),
                dict(notebook='O12i_Upgrade.ipynb', path='upgrade.webm'),
                dict(notebook='T12d_Spark.ipynb', path='after.webm'),
            ]
            segments = [dict(recording=i, start=0, end=1) for i in range(3)]
            (results / 'video-manifest.json').write_text(json.dumps(
                dict(recordings=recordings, segments=segments)))
            contents = {}

            def encode(*args, cwd):
                # Follow the real concat lists to track each source recording.
                output = str(Path(args[-1]))
                if '-safe' in args:
                    listing = Path(args[args.index('-i') + 1]).read_text().splitlines()
                    contents[output] = sum((contents[line[6:-1]] for line in listing), [])
                elif '-ss' in args:
                    contents[output] = [Path(args[args.index('-i') + 1]).name]
                else:
                    contents[output] = []  # Title card.

            probe = '{"streams":[{"width":640,"height":360}]}'
            with patch.object(render_movie.subprocess, 'check_output', return_value=probe), \
                    patch.object(render_movie, 'ffmpeg', side_effect=encode):
                render_movie.render(results, 'upgrade-3.2.2-3.3.6-basic')
            self.assertEqual(contents[str(results / 'movies/notebooks-upgrade-3.2.2-3.3.6-basic.mp4')],
                             ['before.webm', 'upgrade.webm', 'after.webm'])
            self.assertEqual(contents[str(results / 'movies/T12d.mp4')],
                             ['before.webm', 'after.webm'])


if __name__ == '__main__':
    unittest.main()
