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


def send_control(path, text):
    """Commands for a running game in its control file (--rexnative_d3d_control), which the game
    reads and removes the moment it sees it: the file appears whole (written aside, then linked in
    place), as an append could be seen empty and its commands lost (a route's START, and the game
    stayed on its title screen; ReXNative's renderer/src/native/control_file.h). One the game has
    not taken yet is waited for (3 s), then added to."""
    text = text + '\n'
    tmp = '%s.%d.tmp' % (path, os.getpid())
    with open(tmp, 'w', encoding='ascii', newline='\n') as f:
        f.write(text)
    try:
        for _ in range(60):
            try:
                os.link(tmp, path)  # only where there is none
                return
            except (FileExistsError, PermissionError):  # there is one, or it is being removed
                pass
            except OSError:  # a file system without hard links
                try:
                    if not os.path.exists(path):
                        os.replace(tmp, path)
                        return
                except PermissionError:
                    pass
            time.sleep(0.05)
        with open(path, 'a', encoding='ascii', newline='\n') as f:
            f.write(text)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
