"""Core OCR data shapes shared by the engine and every feature."""
from dataclasses import dataclass, field


@dataclass
class Word:
    """One recognized word: text + absolute pixel box on the full image + 0-100 confidence."""
    text: str
    conf: float
    x: int
    y: int
    w: int
    h: int

    def shifted(self, dx: int, dy: int, scale: float = 1.0) -> "Word":
        """Map a word from tile coordinates back onto the full image."""
        return Word(self.text, self.conf,
                    round(self.x / scale) + dx, round(self.y / scale) + dy,
                    round(self.w / scale), round(self.h / scale))


@dataclass
class SectionResult:
    """Outcome of scanning one Sectioned-Scan tile."""
    idx: int
    bbox: tuple[int, int, int, int]      # [x, y, w, h] on the full image
    words: list[Word] = field(default_factory=list)
    mean_conf: float = 0.0
    status: str = "ok"                   # ok | low_conf | unreadable
    crop_path: str | None = None
    rescued: bool = False                # local rescue pass fixed this section (additive field)
    rescue_method: str | None = None     # which variant won, e.g. "zoom4+binarize" / "rotate90"


@dataclass
class JobResult:
    """Everything one Job produced — becomes result.json + DB rows (the Raw Extract)."""
    job_id: int
    source_path: str
    job_dir: str
    full_text: str = ""
    mean_conf: float = 0.0
    words: list[Word] = field(default_factory=list)
    sections: list[SectionResult] = field(default_factory=list)
    page: int | None = None              # 1-based page number when the Source is a PDF
    pages: int | None = None             # total pages of that PDF
    languages_used: str | None = None    # actual OCR languages after auto-detect (additive, v0.1.3)
    page_rotation: int = 0               # degrees CW the page was turned to be upright (additive, v0.1.5)
    page_size_mm: tuple[float, float] | None = None  # physical paper size driving the grid (additive, v0.1.5)
