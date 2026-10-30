"""Package source and recorded evidence; exclude environments, caches and databases."""
import argparse,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('output');args=p.parse_args();out=Path(args.output).resolve()
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for path in root.rglob('*'):
        if path==out:continue
        if path.is_file() and not any(part in path.parts for part in ['.git','__pycache__','.pytest_cache','node_modules','.venv','runtime']) and path.suffix not in ['.db','.pyc']:
            z.write(path,Path('qlarity-yield')/path.relative_to(root))
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    assert 'qlarity-yield/README.md' in z.namelist()
print(f'{out}: {out.stat().st_size} bytes')
