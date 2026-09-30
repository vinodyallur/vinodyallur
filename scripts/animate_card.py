#!/usr/bin/env python3
"""Add a staggered line reveal to generated gh-ascii SVG cards."""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


SVG_NAMESPACE = "http://www.w3.org/2000/svg"
STYLE_ID = "profile-line-animation"
STYLE = """
.profile-line {
  animation: profile-line-in 0.42s ease-out both;
  transform-box: fill-box;
  transform-origin: left center;
}
@keyframes profile-line-in {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}
@media (prefers-reduced-motion: reduce) {
  .profile-line { animation: none; }
}
""".strip()


def animate_card(path: Path) -> int:
    ET.register_namespace("", SVG_NAMESPACE)
    tree = ET.parse(path)
    root = tree.getroot()

    for element in list(root):
        if element.tag == f"{{{SVG_NAMESPACE}}}style" and element.get("id") == STYLE_ID:
            root.remove(element)

    style = ET.Element(f"{{{SVG_NAMESPACE}}}style", {"id": STYLE_ID})
    style.text = STYLE
    root.insert(0, style)

    text_elements = root.findall(f".//{{{SVG_NAMESPACE}}}text")
    for index, element in enumerate(text_elements):
        classes = set(element.get("class", "").split())
        classes.add("profile-line")
        element.set("class", " ".join(sorted(classes)))
        element.set("style", f"animation-delay: {index * 35}ms")

    tree.write(path, encoding="unicode", xml_declaration=False, short_empty_elements=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write("\n")
    return len(text_elements)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cards", nargs="+", type=Path)
    arguments = parser.parse_args()

    for card in arguments.cards:
        count = animate_card(card)
        print(f"Animated {count} lines in {card}")


if __name__ == "__main__":
    main()