from __future__ import annotations


def parse_archive_post_text(text: str) -> dict:
    sections: dict[str, dict[str, list[str]]] = {}
    current_title = ""
    current_section = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            current_title = line[2:].strip()
            sections[current_title] = {}
            current_section = ""
        elif line.startswith("## "):
            if not current_title:
                raise ValueError("Section found before title.")
            current_section = line[3:].strip()
            sections[current_title][current_section] = []
        elif current_title and current_section:
            sections[current_title][current_section].append(line)
    if len(sections) != 1:
        raise ValueError("Expected exactly one top-level post title.")
    title, post_sections = next(iter(sections.items()))
    if "Versions" not in post_sections:
        raise ValueError("Required section Versions is missing.")
    if "Description" not in post_sections:
        raise ValueError("Required section Description is missing.")
    return {"title": title, "sections": post_sections}


def slugify(text: str) -> str:
    import re

    text = text.lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")
