"""Split gui_main.py tab classes into scripts/client/tabs/."""
import re
from pathlib import Path

HEADER = Path("scripts/client/gui_main.py").read_text(encoding="utf-8").split("class PortfolioHistoryTab")[0]
text = Path("scripts/client/gui_main.py").read_text(encoding="utf-8")
classes = list(re.finditer(r"^class (\w+)", text, re.M))
SKIP = {"IBTransactionsTab", "MainWindow", "_TabLoader"}

tabs_dir = Path("scripts/client/tabs")
tabs_dir.mkdir(exist_ok=True)

tab_imports = []
for i, m in enumerate(classes):
    name = m.group(1)
    if name in SKIP:
        continue
    start = m.start()
    end = classes[i + 1].start() if i + 1 < len(classes) else text.find("class _TabLoader")
    if name == "SettingsTab":
        end = text.find("class _TabLoader")
    body = text[start:end].rstrip() + "\n"
    fname = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower().lstrip("_") + ".py"
    if fname.startswith("keys_sub"):
        fname = "keys_sub_tab.py"
    module = fname.replace(".py", "")
    content = (
        '"""Auto-split from gui_main."""\n\n'
        + HEADER
        + "\n"
        + body
    )
    (tabs_dir / fname).write_text(content, encoding="utf-8")
    tab_imports.append((name, module, fname))

init_lines = ["# Tab widgets package\n"]
for name, module, _ in tab_imports:
    init_lines.append(f"from scripts.client.tabs.{module} import {name}\n")
(tabs_dir / "__init__.py").write_text("".join(init_lines), encoding="utf-8")
print(f"Created {len(tab_imports)} tab modules")
