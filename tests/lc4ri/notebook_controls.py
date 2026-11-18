"""Operate JupyterLab notebook cells through the visible controls."""
from types import SimpleNamespace


def source(cell):
    value = cell['source']
    return ''.join(value) if isinstance(value, list) else value


def operations(page, key, reference, records, timeout=120000):
    edits = {}

    def find(fragment):
        indices = [i for i, cell in enumerate(reference['cells'])
                   if cell['cell_type'] == 'code' and fragment in source(cell)]
        assert len(indices) == 1, (fragment, indices)
        return indices[0]

    def state(index):
        return page.evaluate('''i => {
            const cell = window.jupyterapp.shell.currentWidget.content.widgets[i];
            const flags = cell.model.getMetadata('run_through_control');
            return {frozen: !!(flags && flags.frozen),
                readOnly: cell.model.getMetadata('editable') === false,
                count: cell.model.executionCount,
                text: cell.model.sharedModel.getSource(), outputs: cell.model.outputs.toJSON()};
        }''', index)

    def select(index):
        page.evaluate('async i => {await window.jupyterapp.shell.currentWidget.content.scrollToItem(i);}', index)
        cell = page.locator(f'.jp-NotebookPanel:visible .jp-Cell[data-windowed-list-index="{index}"]')
        cell.locator('.jp-InputArea-prompt').click()
        page.keyboard.press('Escape')
        assert page.evaluate('window.jupyterapp.shell.currentWidget.content.activeCellIndex') == index
        return cell

    def unfreeze(index):
        select(index)
        if state(index)['frozen']:
            page.get_by_title('unfreeze selected cells', exact=True).click()
            assert not state(index)['frozen']
        if state(index)['readOnly']:
            page.get_by_title('make selected cells editable', exact=True).click()
            assert not state(index)['readOnly']

    def edit(index, text, reason):
        unfreeze(index)
        before = state(index)['text']
        select(index).locator('.cm-content').click()
        page.keyboard.press('Control+A')
        page.keyboard.insert_text(text)
        assert state(index)['text'] == text
        edits[index] = text
        records.append(dict(notebook=key, cell=index, action='edit input', reason=reason,
                            before=before, after=text))

    def run(index):
        unfreeze(index)
        select(index)
        before = state(index)['count']
        print(f'LC4RI EXEC: {key} cell {index}', flush=True)
        page.keyboard.press('Shift+Enter')
        page.wait_for_function('''({i,before}) => {
            const panel = window.jupyterapp.shell.currentWidget;
            const cell = panel.content.widgets[i];
            const flags = cell.model.getMetadata('run_through_control');
            return cell.model.executionCount !== null && cell.model.executionCount !== before &&
                panel.sessionContext.session.kernel.status === 'idle' &&
                ((flags && flags.frozen) || cell.model.outputs.toJSON().some(o => o.output_type === 'error'));
        }''', arg=dict(i=index, before=before), timeout=timeout)
        observed = state(index)
        errors = [output for output in observed['outputs'] if output['output_type'] == 'error']
        records.append(dict(notebook=key, cell=index, action='Shift+Enter',
                            errors=errors, execution_count=observed['count']))
        if errors:
            for output in observed['outputs']:
                if output['output_type'] == 'stream':
                    print(output['text'], end='', flush=True)
        assert not errors, errors
        assert observed['frozen'] and observed['readOnly'], observed
        return observed

    return SimpleNamespace(find=find, state=state, edit=edit, run=run, edits=edits)
