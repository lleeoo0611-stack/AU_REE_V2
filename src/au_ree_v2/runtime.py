"""Record the analytical runtime alongside each integrated Census release."""
from importlib import import_module
from pathlib import Path
import os
import platform
import shutil
import sqlite3
import subprocess

from .store import filehash


def version_line(command):
    if not command:
        return None
    try:
        result = subprocess.run([command, '--version'], capture_output=True, text=True,
                                errors='replace', timeout=15)
        lines = (result.stdout or result.stderr).splitlines()
        return lines[0] if lines and result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def analytical_runtime(root, tessdata, rscript):
    tessdata = tessdata or os.environ.get('TESSDATA_PREFIX')
    model = Path(tessdata)/'eng.traineddata' if tessdata else None
    constraints = Path(root)/'requirements-constraints.txt'
    return dict(python=platform.python_version(), sqlite=sqlite3.sqlite_version,
                packages={name:import_module(name.lower()).__version__ for name in ('shapely','pyproj','pypdf','PyMuPDF',
                                                           'openpyxl','numpy','certifi','et_xmlfile')},
                r=version_line(rscript or shutil.which('Rscript')),
                tesseract=version_line(os.environ.get('TESSERACT') or shutil.which('tesseract')),
                ocr_eng_sha256=filehash(model) if model and model.is_file() else None,
                constraints_sha256=filehash(constraints) if constraints.is_file() else None)
