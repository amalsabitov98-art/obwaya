"""Общие мелочи для сборки .ipynb из обычных питон-строк."""

import json
from pathlib import Path


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def code(text, form=True):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"cellView": "form"} if form else {},
        "outputs": [],
        "source": text.splitlines(True),
    }


def write(path: Path, cells):
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": [], "toc_visible": True},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Записал {path} ({path.stat().st_size} байт, {len(cells)} ячеек)")
