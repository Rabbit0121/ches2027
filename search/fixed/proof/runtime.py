"""Module execution and anonymous file references for proof stages."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PACKAGE = 'ches2027.search.fixed.proof'
REFERENCE = 'the/path/of/proof_results'


def configure(output):
    os.environ['CHES_PROOF_SOURCE'] = str(ROOT)
    os.environ['CHES_PROOF_OUTPUT'] = str(Path(output).resolve())


def work_root():
    if 'CHES_PROOF_OUTPUT' not in os.environ:
        if '--output' not in sys.argv:
            raise ValueError('A proof output location is required')
        path = Path(sys.argv[sys.argv.index('--output') + 1]).resolve()
        configure(path.parent if path.suffix == '.json' else path)
    return Path(os.environ['CHES_PROOF_OUTPUT'])


def work_reference(path):
    relative = Path(path).resolve().relative_to(work_root())
    return REFERENCE + ('/' + relative.as_posix() if relative.parts else '')


def work_path(reference):
    if not reference.startswith(REFERENCE):
        raise ValueError('Expected an anonymous proof reference')
    path = (work_root() / reference[len(REFERENCE):].lstrip('/')).resolve()
    path.relative_to(work_root())
    return path


def work_relative(path):
    return Path(path).resolve().relative_to(work_root()).as_posix()


def quote(path):
    path = Path(path).resolve()
    if path.is_relative_to(ROOT):
        variable, relative = 'CHES_PROOF_SOURCE', path.relative_to(ROOT)
    else:
        variable, relative = 'CHES_PROOF_OUTPUT', path.relative_to(work_root())
    value = relative.as_posix().replace("'", "''") or '.'
    return "(Join-Path $env:" + variable + " '" + value + "')"


def fail(error):
    print(type(error).__name__ + ': proof stage failed', file=sys.stderr)
    raise SystemExit(1)


def run(command, **kwargs):
    command = list(command)
    output = work_root()
    env = dict(os.environ, **kwargs.pop('env', {}))
    env['CHES_PROOF_SOURCE'], env['CHES_PROOF_OUTPUT'] = str(ROOT), str(output)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = str(ROOT.parents[3]) + os.pathsep + env.get('PYTHONPATH', '')
    if str(command[0]) == sys.executable:
        script = Path(command[1]).resolve().relative_to(ROOT).with_suffix('')
        module = PACKAGE + '.' + '.'.join(script.parts)
        command = [sys.executable, '-B', '-m', module, *map(str, command[2:])]
    elif '-File' in command:
        script = Path(command[command.index('-File') + 1])
        text = script.read_text(encoding='utf-8-sig')
        if not text.startswith('# Anonymous proof worker'):
            script.write_text('# Anonymous proof worker\ntry {\n' + text +
                "\n} catch { [Console]::Error.WriteLine('Proof worker failed: ' + $_.Exception.GetType().Name); exit 1 }\n")
    kwargs.setdefault('cwd', output if output.exists() else output.parent)
    return subprocess.run(command, env=env, **kwargs)
