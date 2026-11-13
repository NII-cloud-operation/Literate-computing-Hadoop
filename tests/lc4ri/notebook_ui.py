"""Run notebook working copies through LC4RI's browser controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote
import uuid
import urllib.request

from playwright.sync_api import sync_playwright, expect

from browser_evidence import recorded_context, finish_recording
from notebook_controls import operations, source
from scenario import run

BASE = 'http://127.0.0.1:18888'


class NotebookSession:
    def __init__(self, context, repo, results, token):
        self.context = context
        self.repo = repo
        self.results = results
        self.token = token
        self.records = []
        self.coverage = {}
        self.hashes = {}
        self.completed = []
        self.page = None

    def api(self, path, method='GET', body=None):
        request = urllib.request.Request(BASE + '/api/' + path, method=method,
            headers={'Authorization': 'token ' + self.token, 'Content-Type': 'application/json'},
            data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def read_file(self, path):
        return self.api('contents/' + quote(path, safe='/'))['content']

    def open_document(self, filename):
        page = self.context.new_page()
        workspace = uuid.uuid4().hex
        page.goto(BASE + '/lab/workspaces/' + workspace + '/tree/' + quote(filename, safe='/') + '?token=' + self.token)
        page.wait_for_function('''name => window.jupyterapp && window.jupyterapp.shell.currentWidget &&
            window.jupyterapp.shell.currentWidget.context.path === name''', arg=filename, timeout=120000)
        return page

    def menu_command(self, page, menu, command):
        page.locator('.lm-MenuBar-itemLabel').filter(has_text=re.compile('^' + menu + '$')).click()
        page.locator('.lm-Menu-item[data-command="' + command + '"]:visible').click()

    def edit_file(self, path, text):
        before = self.read_file(path)
        page = self.open_document(path)
        try:
            page.locator('.jp-DirListing-itemText').filter(
                has_text=re.compile('^' + re.escape(Path(path).name) + '$')).click(button='right')
            page.locator('.lm-Menu-itemLabel').filter(has_text=re.compile('^Open With$')).hover()
            page.get_by_role('menuitem', name='Editor', exact=True).click()
            page.locator('.jp-FileEditor .cm-content').click()
            page.keyboard.press('Control+A')
            page.keyboard.insert_text(text)
            page.keyboard.press('Control+s')
            page.wait_for_function('!window.jupyterapp.shell.currentWidget.context.model.dirty')
            assert self.read_file(path) == text, path
            page.screenshot(path=str(self.results / (path.replace('/', '-') + '.png')), full_page=True)
            self.records.append(dict(action='edit file', path=path, before=before, after=text))
        finally:
            page.close()

    def run_notebook(self, filename, before_cell=None):
        path = self.repo / filename
        key = path.stem.split('_', 1)[0]
        raw = path.read_bytes()
        reference = json.loads(raw)
        self.hashes[filename] = hashlib.sha256(raw).hexdigest()
        kernel = reference['metadata']['kernelspec']['name']
        available = self.api('kernelspecs')['kernelspecs']
        assert kernel in available, f'{filename} requires kernel {kernel}; available: {list(available)}'
        template = filename
        self.api('contents/' + quote(template, safe='/'), 'PUT',
                 dict(type='notebook', format='json', content=reference))
        self.page = self.open_document(template)
        try:
            expect(self.page.get_by_title('unfreeze selected cells', exact=True)).to_be_visible()
            document = key + '-working-' + uuid.uuid4().hex + '.ipynb'
            self.menu_command(self.page, 'File', 'docmanager:save-as')
            self.page.locator('.jp-Dialog input').fill(document)
            self.page.locator('.jp-Dialog button.jp-mod-accept').click()
            self.page.wait_for_function('''name =>
                (window.jupyterapp.shell.currentWidget && window.jupyterapp.shell.currentWidget.context.path === name) ||
                Array.from(document.querySelectorAll('.jp-Dialog')).some(d => d.textContent.includes('Save your work'))''',
                arg=document)
            dialog = self.page.locator('.jp-Dialog')
            if dialog.is_visible():
                expect(dialog).to_contain_text('Save your work')
                dialog.get_by_role('button', name='Discard changes to file', exact=True).click()
            self.page.locator('.lm-TabBar-tabLabel').filter(has_text=document).click()
            self.page.wait_for_function('name => window.jupyterapp.shell.currentWidget && window.jupyterapp.shell.currentWidget.context.path === name', arg=document)
            self.page.evaluate('async () => {await window.jupyterapp.shell.currentWidget.sessionContext.ready;}')
            self.page.wait_for_function('window.jupyterapp.shell.currentWidget.sessionContext.session.kernel.connectionStatus === "connected"', timeout=120000)
            assert self.page.evaluate('window.jupyterapp.shell.currentWidget.context.model.toJSON().cells.map(c => c.source)') == [source(c) for c in reference['cells']]
            self.menu_command(self.page, 'Edit', 'editmenu:clear-all')
            assert self.page.evaluate("window.jupyterapp.shell.currentWidget.context.model.toJSON().cells.filter(c => c.cell_type === 'code').every(c => c.outputs.length === 0)")
            controls = operations(self.page, key, reference, self.records, timeout=1200000)
            self.coverage[filename] = dict(attempted=[], completed=[])
            for index, cell in enumerate(reference['cells']):
                text = source(cell)
                if cell['cell_type'] != 'code' or not text.strip():
                    continue
                if before_cell is not None:
                    before_cell(self, controls, index, text)
                self.coverage[filename]['attempted'].append(index)
                controls.run(index)
                self.coverage[filename]['completed'].append(index)
            self.page.keyboard.press('Control+s')
            self.page.wait_for_function('!window.jupyterapp.shell.currentWidget.context.model.dirty')
            saved = self.read_file(document)
            for index, cell in enumerate(reference['cells']):
                expected = controls.edits[index] if index in controls.edits else source(cell)
                assert source(saved['cells'][index]) == expected, (filename, index)
            assert path.read_bytes() == raw, filename
            self.completed.append(filename)
        finally:
            if self.page.evaluate('window.jupyterapp.shell.currentWidget !== null'):
                saved = self.page.evaluate('window.jupyterapp.shell.currentWidget.context.model.toJSON()')
                (self.results / (key + '-working.ipynb')).write_text(json.dumps(saved, ensure_ascii=False, indent=1) + '\n')
            self.page.screenshot(path=str(self.results / (key + '.png')), full_page=True)
            self.page.close()
            self.page = None

    def save_report(self, error):
        (self.results / 'source-hashes.json').write_text(json.dumps(self.hashes, indent=2) + '\n')
        report = dict(status='passed' if error is None else 'failed', error=str(error) if error is not None else None,
                      completed=self.completed, coverage=self.coverage, operations=self.records)
        (self.results / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result-dir', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    results = args.result_dir.resolve()
    results.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = recorded_context(browser, results / 'videos', viewport={'width': 1600, 'height': 1000})
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        session = NotebookSession(context, repo, results, os.environ['LC4RI_TEST_TOKEN'])
        try:
            workspace = context.new_page()
            workspace.goto(BASE + '/lab?token=' + session.token)
            run(session)
        finally:
            session.save_report(sys.exc_info()[1])
            finish_recording(context, results / 'browser-trace.zip', results / 'videos')
            browser.close()


if __name__ == '__main__':
    main()
