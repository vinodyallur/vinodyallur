#!/usr/bin/env python3
"""Merge fresh gh-ascii data rows while preserving the current portrait."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import xml.etree.ElementTree as ET


SVG_NAMESPACE = "http://www.w3.org/2000/svg"
TEXT_TAG = f"{{{SVG_NAMESPACE}}}text"
RECT_TAG = f"{{{SVG_NAMESPACE}}}rect"
PORTRAIT_FONT_SIZE = 8.0
REMOVED_METRICS = (". Stars:", ". Followers:", ". Contributed:", ". Issues:")
TOP_REPO_STARS = re.compile(r"\s+\([\d,]+\s*\u2605\)\s*$")


def number(value: str) -> float:
    return float(value.removesuffix("px"))


def format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def text_rows(root: ET.Element, portrait: bool) -> list[ET.Element]:
    rows = []
    for element in root.findall(TEXT_TAG):
        font_size = number(element.get("font-size", "0"))
        if (font_size <= PORTRAIT_FONT_SIZE) == portrait:
            rows.append(element)
    return rows


def portrait_signature(root: ET.Element) -> list[tuple[tuple[tuple[str, str], ...], str]]:
    return [
        (tuple(sorted(element.attrib.items())), "".join(element.itertext()))
        for element in text_rows(root, portrait=True)
    ]


def ensure_metric_minimum(row: ET.Element, label: str, minimum: int) -> None:
    children = list(row)
    label_index = next(
        (index for index, child in enumerate(children) if label in (child.text or "")),
        None,
    )
    if label_index is None:
        raise RuntimeError(f"Fresh card is missing the {label} metric")

    for child in children[label_index + 1 :]:
        value = (child.text or "").strip().replace(",", "")
        if value.isdigit():
            child.text = f" {max(int(value), minimum):,}"
            return
    raise RuntimeError(f"Fresh card has no numeric value for {label}")


def simplify_data_rows(
    rows: list[ET.Element],
    minimum_repos: int,
    minimum_contributions: int,
) -> None:
    for row in rows:
        row_text = "".join(row.itertext())
        for label in REMOVED_METRICS:
            if label not in row_text:
                continue
            children = list(row)
            label_index = next(
                index
                for index, child in enumerate(children)
                if label in (child.text or "")
            )
            start = label_index
            if label_index > 0 and (children[label_index - 1].text or "").strip() == "|":
                start -= 1
            for child in children[start:]:
                row.remove(child)
            break

        if ". Top repo:" in row_text:
            for child in reversed(list(row)):
                if child.text:
                    child.text = TOP_REPO_STARS.sub("", child.text)
                    break

        if ". Repos:" in row_text:
            ensure_metric_minimum(row, ". Repos:", minimum_repos)
        if ". Contributions:" in row_text:
            ensure_metric_minimum(row, ". Contributions:", minimum_contributions)


def update_dimensions(
    current_root: ET.Element,
    fresh_root: ET.Element,
    current_data_x: float,
    fresh_data_x: float,
) -> None:
    current_height = number(current_root.get("height", "0"))
    fresh_width = number(fresh_root.get("width", "0"))
    fresh_height = number(fresh_root.get("height", "0"))
    merged_width = current_data_x + (fresh_width - fresh_data_x)
    merged_height = max(current_height, fresh_height)

    current_root.set("width", format_number(merged_width))
    current_root.set("height", format_number(merged_height))
    current_root.set("viewBox", f"0 0 {format_number(merged_width)} {format_number(merged_height)}")

    frame = current_root.find(RECT_TAG)
    if frame is None:
        raise RuntimeError("Current card is missing its background frame")
    frame.set("width", format_number(merged_width - 1))
    frame.set("height", format_number(merged_height - 1))


def merge_data(
    current_path: Path,
    fresh_path: Path,
    minimum_repos: int,
    minimum_contributions: int,
) -> tuple[int, int]:
    ET.register_namespace("", SVG_NAMESPACE)
    current_tree = ET.parse(current_path)
    fresh_tree = ET.parse(fresh_path)
    current_root = current_tree.getroot()
    fresh_root = fresh_tree.getroot()

    before_portrait = portrait_signature(current_root)
    current_data = text_rows(current_root, portrait=False)
    fresh_data = text_rows(fresh_root, portrait=False)
    if not before_portrait:
        raise RuntimeError(f"No portrait rows found in {current_path}")
    if not current_data or not fresh_data:
        raise RuntimeError("Both cards must contain data rows")

    simplify_data_rows(fresh_data, minimum_repos, minimum_contributions)

    current_data_x = min(number(element.get("x", "0")) for element in current_data)
    fresh_data_x = min(number(element.get("x", "0")) for element in fresh_data)
    x_offset = current_data_x - fresh_data_x

    for element in current_data:
        current_root.remove(element)
    for element in fresh_data:
        replacement = deepcopy(element)
        replacement.set("x", format_number(number(replacement.get("x", "0")) + x_offset))
        current_root.append(replacement)

    update_dimensions(current_root, fresh_root, current_data_x, fresh_data_x)
    if portrait_signature(current_root) != before_portrait:
        raise RuntimeError("Portrait rows changed during the data merge")

    current_tree.write(
        current_path,
        encoding="unicode",
        xml_declaration=False,
        short_empty_elements=True,
    )
    with current_path.open("a", encoding="utf-8", newline="\n") as output:
        output.write("\n")
    return len(before_portrait), len(fresh_data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path)
    parser.add_argument("fresh", type=Path)
    parser.add_argument("--minimum-repos", type=int, default=0)
    parser.add_argument("--minimum-contributions", type=int, default=0)
    arguments = parser.parse_args()

    portrait_rows, data_rows = merge_data(
        arguments.current,
        arguments.fresh,
        arguments.minimum_repos,
        arguments.minimum_contributions,
    )
    print(
        f"Preserved {portrait_rows} portrait rows and refreshed {data_rows} data rows "
        f"in {arguments.current}"
    )


if __name__ == "__main__":
    main()