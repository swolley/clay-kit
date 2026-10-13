import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_overlap import main  # noqa: E402


def test_no_arguments_prints_usage_and_returns_2(capsys):
    assert main([]) == 2
    out = capsys.readouterr().out
    assert "Usage" in out and "--zazencodes" in out


def test_help_flag_prints_usage(capsys):
    assert main(["-h"]) == 0
    assert "Usage" in capsys.readouterr().out


def test_missing_folder_is_reported_not_a_traceback(capsys):
    assert main(["/nonexistent/folder/for/test"]) == 2
    assert "not a folder" in capsys.readouterr().out


def test_reports_shared_sequences(tmp_path, capsys):
    other = tmp_path / "other"
    mine = tmp_path / "mine"
    other.mkdir()
    mine.mkdir()
    (other / "a.md").write_text("the quick brown fox jumps over the lazy dog today")
    (mine / "b.md").write_text("we saw the quick brown fox jumps over the lazy cat")
    assert main([str(other), str(mine)]) == 0
    out = capsys.readouterr().out
    assert "b.md" in out and "total shared 6-grams: 3" in out
