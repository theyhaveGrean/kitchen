"""Browse and compare benchmark recipe outputs in a small PyQt6 window."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LATEST_DIR = PROJECT_ROOT / "benchmarks" / "results" / "latest"
REWRITTEN_DIR = PROJECT_ROOT / "benchmarks" / "results" / "rewritten"
BENCHMARK_SCRIPT = PROJECT_ROOT / "benchmarks" / "run.py"
REWRITE_SCRIPT = PROJECT_ROOT / "scripts" / "test_openai.py"
BENCHMARK_SUMMARY = LATEST_DIR / "batch_results.csv"
PROGRESS_LINE = re.compile(r"^\[(\d+)/(\d+)\]\s+(.+)$")


def load_recipe(path: Path | None) -> dict[str, Any] | str:
    """Load a recipe object, returning an error message when it cannot be read."""
    if path is None:
        return "No matching result file."
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Could not read {path.name}: {exc}"
    return data if isinstance(data, dict) else {"_value": data}


def display_items(value: Any) -> list[str]:
    if value is None:
        return ["No data"]
    if isinstance(value, list):
        rendered = []
        for item in value:
            if isinstance(item, dict) and "ingredient" in item:
                parts = [str(item[key]) for key in ("quantity", "unit", "ingredient") if item.get(key)]
                line = " ".join(parts)
                if item.get("preparation_type"):
                    line += f", {item['preparation_type']}"
                rendered.append(line)
            else:
                rendered.append(str(item))
        return rendered or ["No items"]
    return [str(value)]


def make_section(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    heading = QLabel(title)
    heading.setObjectName("sectionHeading")
    layout.addWidget(heading)
    return card, layout


def make_list(items: list[str], ordered: bool = False) -> QWidget:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for index, item in enumerate(items, 1):
        row = QHBoxLayout()
        row.setSpacing(10)
        marker = QLabel(f"{index:02}" if ordered else "•")
        marker.setObjectName("stepNumber" if ordered else "bullet")
        marker.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        text = QLabel(item)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setObjectName("itemText")
        row.addWidget(marker, 0)
        row.addWidget(text, 1)
        layout.addLayout(row)
    layout.addStretch(1)
    return content


class ResultsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Recipe Results Comparison")
        self.resize(1440, 900)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f4f6fa; color: #20283a; }
            QListWidget { background: white; border: 1px solid #e1e6ef; border-radius: 10px;
                          padding: 6px; font-size: 13px; }
            QListWidget::item { padding: 10px 8px; border-radius: 6px; }
            QListWidget::item:selected { background: #e8efff; color: #244da8; }
            QLabel#recipeTitle { font-size: 22px; font-weight: 700; color: #182238; }
            QLabel#source { color: #66738a; }
            QLabel#columnHeading { font-size: 16px; font-weight: 700; padding: 8px 2px; }
            QLabel#sectionHeading { font-size: 14px; font-weight: 700; color: #3a4b68; }
            QFrame#card { background: white; border: 1px solid #e1e6ef; border-radius: 10px; }
            QLabel#itemText { font-size: 13px; line-height: 1.4; }
            QLabel#bullet { color: #6683c4; font-size: 16px; min-width: 16px; }
            QLabel#stepNumber { color: #486ab3; font-size: 11px; font-weight: 700;
                                background: #edf2ff; border-radius: 10px; min-width: 28px;
                                min-height: 24px; padding-top: 4px; }
            QScrollArea { border: none; background: transparent; }
            QSplitter::handle { background: #e7ebf2; }
            QPushButton { background: #375fbd; color: white; border: none; border-radius: 6px;
                          padding: 8px 14px; font-weight: 600; }
            QPushButton:disabled { background: #aab5cd; }
            QProgressBar { border: 1px solid #dce3f0; border-radius: 5px;
                           background: white; text-align: center; height: 18px; }
            QProgressBar::chunk { background: #7193e0; border-radius: 4px; }
            QPlainTextEdit { background: #202a3e; color: #e8efff; border: none;
                             border-radius: 7px; padding: 8px; font-size: 12px; }
        """)

        self.recipe_list = QListWidget()
        self.recipe_list.setMinimumWidth(220)
        self.recipe_list.currentItemChanged.connect(self.show_selected)

        self.recipe_title = QLabel("Select a recipe")
        self.recipe_title.setObjectName("recipeTitle")
        self.source_label = QLabel()
        self.source_label.setObjectName("source")
        self.latest_heading = QLabel("LATEST")
        self.latest_heading.setObjectName("columnHeading")
        self.rewritten_heading = QLabel("REWRITTEN")
        self.rewritten_heading.setObjectName("columnHeading")
        self.latest_ingredients = QWidget()
        self.latest_steps = QWidget()
        self.rewritten_ingredients = QWidget()
        self.rewritten_steps = QWidget()

        latest_panel = self.make_recipe_column("Latest", self.latest_heading, self.latest_ingredients, self.latest_steps)
        rewritten_panel = self.make_recipe_column(
            "Rewritten", self.rewritten_heading, self.rewritten_ingredients, self.rewritten_steps
        )

        header = QVBoxLayout()
        header.setSpacing(3)
        header.addWidget(self.recipe_title)
        header.addWidget(self.source_label)

        self.run_button = QPushButton("Run full pipeline")
        self.run_button.clicked.connect(self.run_benchmark)
        self.postprocess_button = QPushButton("Post-process saved results")
        self.postprocess_button.setToolTip("Normalize and rewrite JSON files already in the latest results directory")
        self.postprocess_button.clicked.connect(self.run_postprocess)
        start_label = QLabel("Start at")
        self.start_row = QSpinBox()
        self.start_row.setRange(1, 100000)
        self.start_row.setValue(1)
        self.start_row.setToolTip("First dataset row to process, starting at 1")
        count_label = QLabel("Count")
        self.recipe_count = QSpinBox()
        self.recipe_count.setRange(0, 100000)
        self.recipe_count.setSpecialValueText("All")
        self.recipe_count.setValue(10)
        self.recipe_count.setToolTip("Number of recipes to process; All runs from Start at to the end")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label = QLabel("Pipeline ready")
        self.benchmark_log = QPlainTextEdit()
        self.benchmark_log.setReadOnly(True)
        self.benchmark_log.setMaximumHeight(150)
        benchmark_row = QHBoxLayout()
        benchmark_row.addWidget(start_label)
        benchmark_row.addWidget(self.start_row)
        benchmark_row.addWidget(count_label)
        benchmark_row.addWidget(self.recipe_count)
        benchmark_row.addWidget(self.run_button)
        benchmark_row.addWidget(self.postprocess_button)
        benchmark_row.addWidget(self.progress_bar, 1)
        benchmark_row.addWidget(self.status_label, 2)

        self.benchmark_process = QProcess(self)
        self.benchmark_process.setWorkingDirectory(str(PROJECT_ROOT))
        self.benchmark_process.readyReadStandardOutput.connect(self.read_benchmark_output)
        self.benchmark_process.readyReadStandardError.connect(self.read_benchmark_error)
        self.benchmark_process.finished.connect(self.benchmark_finished)
        self.benchmark_process.errorOccurred.connect(self.benchmark_error)
        self._stdout_buffer = ""
        self._completed = 0
        self._failures = 0
        self._total = 0
        self._stage = "idle"
        self._extraction_failures = 0
        self._summary_written = False
        self._rewrite_status: dict[str, str] = {}

        results_splitter = QSplitter(Qt.Orientation.Horizontal)
        results_splitter.addWidget(latest_panel)
        results_splitter.addWidget(rewritten_panel)
        results_splitter.setStretchFactor(0, 1)
        results_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.recipe_list)
        main_splitter.addWidget(results_splitter)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 16, 18, 18)
        body_layout.setSpacing(12)
        body_layout.addLayout(header)
        body_layout.addLayout(benchmark_row)
        body_layout.addWidget(self.benchmark_log)
        body_layout.addWidget(main_splitter, 1)
        self.setCentralWidget(body)

        self.paths: dict[str, tuple[Path | None, Path | None]] = {}
        self.load_recipes()

    @staticmethod
    def make_recipe_column(
        name: str, heading: QLabel, ingredients_host: QWidget, steps_host: QWidget
    ) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(10, 4, 4, 4)
        layout.setSpacing(10)
        ingredients_card, ingredients_layout = make_section("Ingredients")
        ingredients_scroll = QScrollArea()
        ingredients_scroll.setWidgetResizable(True)
        ingredients_scroll.setWidget(ingredients_host)
        ingredients_scroll.setMinimumHeight(190)
        ingredients_layout.addWidget(ingredients_scroll)
        steps_card, steps_layout = make_section("Steps")
        steps_scroll = QScrollArea()
        steps_scroll.setWidgetResizable(True)
        steps_scroll.setWidget(steps_host)
        steps_layout.addWidget(steps_scroll)
        heading.setText(name.upper())
        layout.addWidget(heading)
        layout.addWidget(ingredients_card, 0)
        layout.addWidget(steps_card, 1)
        return column

    def load_recipes(self) -> None:
        selected = self.recipe_list.currentItem()
        selected_filename = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.recipe_list.blockSignals(True)
        self.recipe_list.clear()
        self.paths.clear()
        latest_files = {path.name: path for path in LATEST_DIR.glob("*.json")}
        rewritten_files = {path.name: path for path in REWRITTEN_DIR.glob("*.json")}
        filenames = sorted(latest_files.keys() | rewritten_files.keys())
        for filename in filenames:
            latest_path = latest_files.get(filename)
            rewritten_path = rewritten_files.get(filename)
            rewrite_status = self._rewrite_status.get(filename)
            if rewrite_status and rewrite_status != "success":
                rewritten_path = None
            self.paths[filename] = (latest_path, rewritten_path)
            suffix = (
                f"  [rewrite {rewrite_status}]" if rewrite_status and rewrite_status != "success"
                else "" if latest_path and rewritten_path
                else "  [latest only]" if latest_path else "  [rewritten only]"
            )
            self.recipe_list.addItem(Path(filename).stem + suffix)
            self.recipe_list.item(self.recipe_list.count() - 1).setData(Qt.ItemDataRole.UserRole, filename)

        if not filenames:
            self.recipe_list.addItem("No JSON results found")
            self.recipe_list.blockSignals(False)
            return
        row = filenames.index(selected_filename) if selected_filename in filenames else 0
        self.recipe_list.setCurrentRow(row)
        self.recipe_list.blockSignals(False)
        self.show_selected(self.recipe_list.currentItem())

    def run_benchmark(self) -> None:
        if self.benchmark_process.state() != QProcess.ProcessState.NotRunning:
            return
        self._stage = "extract"
        self._stdout_buffer = ""
        self._completed = 0
        self._failures = 0
        self._total = 0
        self._extraction_failures = 0
        self._summary_written = False
        self._rewrite_status.clear()
        self.benchmark_log.clear()
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Starting extraction benchmark...")
        self.run_button.setEnabled(False)
        self.start_row.setEnabled(False)
        self.recipe_count.setEnabled(False)
        arguments = ["-u", str(BENCHMARK_SCRIPT), "--output-dir", str(LATEST_DIR),
                     "--start", str(self.start_row.value())]
        if self.recipe_count.value():
            arguments.extend(["--limit", str(self.recipe_count.value())])
        self.benchmark_process.start(
            sys.executable,
            arguments,
        )

    def run_postprocess(self) -> None:
        """Run normalization and rewriting over existing latest result files."""
        if self.benchmark_process.state() != QProcess.ProcessState.NotRunning:
            return
        if not self.rewrite_environment_ready():
            return
        files = sorted(LATEST_DIR.glob("*.json"))
        if not files:
            self.status_label.setText(f"No saved recipe JSON files in {LATEST_DIR}")
            self.benchmark_log.appendPlainText(f"No saved recipe JSON files in {LATEST_DIR}")
            return
        self._stage = "rewrite"
        self._stdout_buffer = ""
        self._completed = 0
        self._failures = 0
        self._total = len(files)
        self._extraction_failures = 0
        self._rewrite_status = {path.name: "pending" for path in files}
        self.benchmark_log.clear()
        self.progress_bar.setRange(0, self._total)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Post-processing {self._total} saved recipes...")
        self.set_processing_controls_enabled(False)
        self.load_recipes()
        self.benchmark_process.start(
            sys.executable,
            ["-u", str(REWRITE_SCRIPT), "--input-dir", str(LATEST_DIR),
             "--output-dir", str(REWRITTEN_DIR)],
        )

    def set_processing_controls_enabled(self, enabled: bool) -> None:
        self.run_button.setEnabled(enabled)
        self.postprocess_button.setEnabled(enabled)
        self.start_row.setEnabled(enabled)
        self.recipe_count.setEnabled(enabled)

    def rewrite_environment_ready(self) -> bool:
        missing = [
            name for name in ("ingredient_parser", "dotenv", "openai")
            if importlib.util.find_spec(name) is None
        ]
        if not missing:
            return True
        self._stage = "idle"
        self.set_processing_controls_enabled(True)
        self.status_label.setText("Rewrite unavailable: Python dependencies missing")
        self.benchmark_log.appendPlainText(
            f"Missing Python modules: {', '.join(missing)}\n"
            f"GUI Python: {sys.executable}\n"
            f"Install from {PROJECT_ROOT}:\n"
            f'"{sys.executable}" -m pip install -e ".[rewrite]"'
        )
        return False

    def read_benchmark_output(self) -> None:
        self._stdout_buffer += bytes(self.benchmark_process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            self.handle_benchmark_line(line.rstrip("\r"))

    def read_benchmark_error(self) -> None:
        message = bytes(self.benchmark_process.readAllStandardError()).decode("utf-8", errors="replace")
        self.benchmark_log.insertPlainText(message)
        self.benchmark_log.ensureCursorVisible()

    def handle_benchmark_line(self, line: str) -> None:
        self.benchmark_log.appendPlainText(line)
        self.benchmark_log.ensureCursorVisible()
        progress = PROGRESS_LINE.match(line)
        if progress:
            index, total, name = progress.groups()
            self._total = int(total)
            self.progress_bar.setRange(0, self._total)
            self.progress_bar.setValue(self._completed)
            action = "Extracting" if self._stage == "extract" else "Rewriting"
            self.status_label.setText(f"{action} {index}/{total}: {name}")
        elif self._stage == "extract" and line.lstrip().startswith(("SUCCESS |", "FAILED |")):
            self._completed += 1
            self._failures += line.lstrip().startswith("FAILED |")
            self.progress_bar.setValue(self._completed)
            self.status_label.setText(
                f"Extracted {self._completed}/{self._total} · {self._failures} failed"
            )
            self.load_recipes()
        elif self._stage == "extract" and line.startswith("Summary:"):
            self._summary_written = True
        elif self._stage == "rewrite" and (" -> " in line or line.startswith("FAILED:")):
            self._completed += 1
            failed = line.startswith("FAILED:")
            self._failures += failed
            filename = line.split(": ", 1)[1].split(":", 1)[0] if failed else line.split(" -> ", 1)[0]
            if filename in self._rewrite_status:
                self._rewrite_status[filename] = "failed" if failed else "success"
            self.progress_bar.setValue(self._completed)
            self.status_label.setText(
                f"Rewritten {self._completed}/{self._total} · {self._failures} failed"
            )
            self.load_recipes()

    def benchmark_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.read_benchmark_output()
        if self._stdout_buffer:
            self.handle_benchmark_line(self._stdout_buffer.rstrip("\r"))
            self._stdout_buffer = ""
        self.read_benchmark_error()
        self.load_recipes()
        if self._stage == "extract":
            self._extraction_failures = self._failures
            if self._summary_written and self._completed > self._failures:
                self.start_rewrite()
                return
            self._stage = "idle"
            self.set_processing_controls_enabled(True)
            self.status_label.setText(
                "Extraction finished with no recipes to rewrite" if self._summary_written
                else f"Extraction stopped (exit code {exit_code})"
            )
        else:
            pending = [name for name, status in self._rewrite_status.items() if status == "pending"]
            for name in pending:
                self._rewrite_status[name] = "failed"
            self._failures += len(pending)
            rewrite_successes = sum(status == "success" for status in self._rewrite_status.values())
            self._stage = "idle"
            self.set_processing_controls_enabled(True)
            self.load_recipes()
            self.status_label.setText(
                f"Pipeline finished: {rewrite_successes} rewritten, "
                f"{self._failures} rewrite failures, {self._extraction_failures} extraction failures"
                if self._total else f"Rewrite stopped (exit code {exit_code})"
            )

    def start_rewrite(self) -> None:
        if not self.rewrite_environment_ready():
            return
        try:
            with BENCHMARK_SUMMARY.open(encoding="utf-8-sig", newline="") as file:
                self._rewrite_status = {
                    Path(row["json_file"]).name: "pending"
                    for row in csv.DictReader(file)
                    if row.get("status") == "success" and row.get("json_file")
                }
        except (OSError, KeyError) as exc:
            self.benchmark_log.appendPlainText(f"Could not read benchmark summary: {exc}")
            self.status_label.setText("Pipeline stopped: benchmark summary unavailable")
            self._stage = "idle"
            self.set_processing_controls_enabled(True)
            return
        self._stage = "rewrite"
        self._stdout_buffer = ""
        self._completed = 0
        self._failures = 0
        self._total = 0
        self.progress_bar.setRange(0, 0)
        self.benchmark_log.appendPlainText("\nNormalizing ingredients and rewriting instructions...")
        self.status_label.setText("Starting ingredient normalization and LLM rewrite...")
        self.load_recipes()
        self.benchmark_process.start(
            sys.executable,
            ["-u", str(REWRITE_SCRIPT), "--input-dir", str(LATEST_DIR),
             "--output-dir", str(REWRITTEN_DIR), "--summary", str(BENCHMARK_SUMMARY)],
        )

    def benchmark_error(self, error: QProcess.ProcessError) -> None:
        self.benchmark_log.appendPlainText(f"Process error: {error.name}")
        self.status_label.setText(f"Benchmark error: {error.name}")
        if error == QProcess.ProcessError.FailedToStart:
            self.set_processing_controls_enabled(True)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.benchmark_process.state() != QProcess.ProcessState.NotRunning:
            self.benchmark_process.kill()
            self.benchmark_process.waitForFinished(2000)
        super().closeEvent(event)

    def show_selected(self, current: Any, _previous: Any = None) -> None:
        if current is None:
            return
        filename = current.data(Qt.ItemDataRole.UserRole)
        if filename not in self.paths:
            return
        latest_path, rewritten_path = self.paths[filename]
        latest = load_recipe(latest_path)
        rewritten = load_recipe(rewritten_path)
        title = latest.get("title") if isinstance(latest, dict) else None
        title = title or (rewritten.get("title") if isinstance(rewritten, dict) else None) or Path(filename).stem
        self.recipe_title.setText(str(title))
        link = latest.get("link") if isinstance(latest, dict) else None
        link = link or (rewritten.get("link") if isinstance(rewritten, dict) else None)
        self.source_label.setText(str(link or ""))
        self.latest_heading.setText("LATEST" if latest_path else "LATEST · MISSING")
        rewrite_status = self._rewrite_status.get(filename)
        self.rewritten_heading.setText(
            "REWRITTEN" if rewritten_path else f"REWRITTEN · {rewrite_status.upper()}"
            if rewrite_status else "REWRITTEN · MISSING"
        )
        self.update_column(self.latest_ingredients, self.latest_steps, latest)
        self.update_column(self.rewritten_ingredients, self.rewritten_steps, rewritten)

    @staticmethod
    def replace_content(host: QWidget, content: QWidget) -> None:
        layout = host.layout()
        if layout is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        layout.addWidget(content)

    def update_column(self, ingredients_host: QWidget, steps_host: QWidget, recipe: dict[str, Any] | str) -> None:
        if isinstance(recipe, str):
            self.replace_content(ingredients_host, QLabel(recipe))
            self.replace_content(steps_host, QLabel(""))
            return
        self.replace_content(ingredients_host, make_list(display_items(recipe.get("ingredients"))))
        self.replace_content(steps_host, make_list(display_items(recipe.get("recipe")), ordered=True))


def main() -> int:
    app = QApplication(sys.argv)
    window = ResultsWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
