"""Guard against stale current-release artifact filenames in installation docs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Installation instructions a user follows *today* to get the current
# release. These must never reference a superseded artifact filename. This
# is deliberately a short, explicit list of the "how do I install right
# now" documents -- not every doc that happens to mention a version number.
# Design/compatibility/changelog/roadmap/research documents intentionally
# discuss historical releases by name for provenance and are out of scope.
CURRENT_INSTALL_DOCS = (
    ROOT / "INSTALL.md",
    ROOT / "docs" / "LINUX_INSTALL.md",
)

# Superseded v4.0.0-alpha1 artifact strings that have previously appeared,
# verbatim, in current-release installation instructions (found stale
# during v4.0.0-rc1 post-publication qualification) and must not reappear
# there. Not a general version-templating check -- just a denylist for the
# specific regression already seen once.
STALE_ARTIFACT_STRINGS = (
    "bytefray-4.0.0a1-py3-none-any.whl",
    "Bytefray-Setup-4.0.0-alpha1.exe",
    "bytefray-4.0.0-alpha1-windows.zip",
    "releases/tag/v4.0.0-alpha1",
)


def test_current_install_docs_do_not_reference_stale_alpha1_artifacts() -> None:
    """Prevent a future edit from reintroducing a stale download/install example."""

    for doc in CURRENT_INSTALL_DOCS:
        text = doc.read_text(encoding="utf-8")
        for stale in STALE_ARTIFACT_STRINGS:
            assert stale not in text, (
                f"{doc.relative_to(ROOT)} still references the superseded "
                f"artifact {stale!r} in what should be current install "
                "instructions"
            )
