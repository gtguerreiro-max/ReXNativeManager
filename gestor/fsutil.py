"""Writing a file in one go on Windows: a temporary file of its own in the same folder (two writers
never share one), then os.replace, retried a few times because an antivirus or a reader holding the
file makes it fail with PermissionError."""
import json
import os
import tempfile
import time


def write_text(path, text, newline='\n'):
    d = os.path.dirname(path) or '.'
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=os.path.basename(path) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline=newline) as f:
            f.write(text)
        for i in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if i == 9:
                    raise
                time.sleep(0.1 * (i + 1))
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def write_json(path, data, **kw):
    kw.setdefault('ensure_ascii', False)
    write_text(path, json.dumps(data, **kw))
