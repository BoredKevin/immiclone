import os
import re
from dashboard.config import TEMPLATES_DIR

_TEMPLATE_CACHE = {"mtime": 0.0, "html": ""}
_INCLUDE_RE = re.compile(r"<!--\s*include:\s*([a-zA-Z0-9_\-/\.]+)\s*-->")

def _max_template_mtime(root_dir):
    """Finds the maximum file modification time among all .html files in root_dir."""
    latest = 0.0
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.endswith(".html"):
                try:
                    fp = os.path.join(dirpath, fn)
                    latest = max(latest, os.path.getmtime(fp))
                except OSError:
                    pass
    return latest

def render_template(template_name="index.html"):
    """
    Renders an HTML template by resolving '<!-- include: partials/filename.html -->' directives.
    Caches the assembled HTML in memory based on directory-wide template file mtimes.
    """
    real_templates = os.path.realpath(TEMPLATES_DIR)
    current_mtime = _max_template_mtime(real_templates)
    
    # Return cached compiled HTML if no template file has changed on disk
    if _TEMPLATE_CACHE["html"] and current_mtime <= _TEMPLATE_CACHE["mtime"]:
        return _TEMPLATE_CACHE["html"]

    base_file = os.path.realpath(os.path.join(real_templates, template_name))
    if not base_file.startswith(real_templates + os.sep) or not os.path.isfile(base_file):
        return "<!-- Template not found -->"

    with open(base_file, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_include(match):
        rel_path = match.group(1).strip()
        part_path = os.path.realpath(os.path.join(real_templates, rel_path))
        if not part_path.startswith(real_templates + os.sep) or not os.path.isfile(part_path):
            return f"<!-- Missing partial: {rel_path} -->"
        try:
            with open(part_path, "r", encoding="utf-8") as pf:
                return pf.read()
        except Exception as e:
            return f"<!-- Error reading partial {rel_path}: {e} -->"

    # Support nested includes up to 3 levels deep
    for _ in range(3):
        if not _INCLUDE_RE.search(content):
            break
        content = _INCLUDE_RE.sub(replace_include, content)

    _TEMPLATE_CACHE["mtime"] = current_mtime
    _TEMPLATE_CACHE["html"] = content
    return content
