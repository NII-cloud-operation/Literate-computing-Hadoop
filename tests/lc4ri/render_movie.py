"""Render notebook chapters and a title-separated movie in operator order."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import textwrap


def ffmpeg(*args, cwd):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-y', *args],
                   cwd=cwd, check=True)


def concat(paths, output, work):
    listing = work / 'concat.txt'
    listing.write_text(''.join(f"file '{path.as_posix()}'\n" for path in paths))
    ffmpeg('-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy',
           '-movflags', '+faststart', str(output), cwd=work)


def render(results, variant):
    results = results.resolve()
    manifest = json.loads((results / 'video-manifest.json').read_text())
    if not manifest['recordings']:
        print('No notebook pages were recorded; movie not generated')
        return
    movies = results / 'movies'
    movies.mkdir(exist_ok=True)
    first = results / manifest['recordings'][0]['path']
    probe = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=width,height', '-of', 'json', str(first)], text=True))['streams'][0]
    width, height = probe['width'], probe['height']
    encoding = ['-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                '-pix_fmt', 'yuv420p', '-r', '25', '-video_track_timescale', '12800']
    chapters = []
    with tempfile.TemporaryDirectory(dir=movies) as directory:
        work = Path(directory)
        notebooks = list(dict.fromkeys(item['notebook'] for item in manifest['recordings']))
        for chapter_index, notebook in enumerate(notebooks):
            title = work / 'title.txt'
            title.write_text(textwrap.fill(notebook.removesuffix('.ipynb'), width=65))
            card = work / f'{chapter_index:02d}-title.mp4'
            ffmpeg('-f', 'lavfi', '-i', f'color=c=0x17202a:s={width}x{height}:r=25:d=2',
                   '-vf', 'drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:'
                   'textfile=title.txt:expansion=none:fontcolor=white:fontsize=32:'
                   'line_spacing=12:x=(w-text_w)/2:y=(h-text_h)/2',
                   *encoding, str(card), cwd=work)
            clips = [card]
            for index, segment in enumerate(manifest['segments']):
                recording = manifest['recordings'][segment['recording']]
                if recording['notebook'] != notebook:
                    continue
                duration = segment['end'] - segment['start']
                assert duration > 0, segment
                clip = work / f'{chapter_index:02d}-{index:03d}.mp4'
                ffmpeg('-ss', f"{segment['start']:.6f}", '-i', str(results / recording['path']),
                       '-t', f'{duration:.6f}', '-vf', 'fps=25,setpts=PTS-STARTPTS',
                       *encoding, str(clip), cwd=work)
                clips.append(clip)
            chapter = movies / (notebook.split('_', 1)[0] + '.mp4')
            concat(clips, chapter, work)
            chapters.append(chapter)
        concat(chapters, movies / f'notebooks-{variant}.mp4', work)
    print(f'Rendered {len(chapters)} notebook chapters and notebooks-{variant}.mp4')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--result-dir', type=Path, required=True)
    parser.add_argument('--variant', required=True, choices=['basic', 'security'])
    args = parser.parse_args()
    render(args.result_dir, args.variant)
