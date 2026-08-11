"""Unit tests for the pure functions of the refactored pipeline."""

import pipeline_refactored as pl


def make_entry(timestamp: str, level: str, message: str) -> pl.LogEntry:
    return pl.LogEntry(timestamp=timestamp, level=level, message=message)


class TestParseLogLine:
    def test_parses_standard_line(self) -> None:
        entry = pl.parse_log_line("2024-01-01 12:00:00 INFO User 42 logged in")
        assert entry == pl.LogEntry("2024-01-01 12:00:00", "INFO", "User 42 logged in")

    def test_parses_api_line(self) -> None:
        entry = pl.parse_log_line("2024-01-01 12:08:00 INFO API /users/profile took 250ms")
        assert entry is not None
        assert entry.level == "INFO"
        assert entry.message == "API /users/profile took 250ms"

    def test_returns_none_for_garbage(self) -> None:
        assert pl.parse_log_line("not a log line") is None

    def test_returns_none_for_empty_line(self) -> None:
        assert pl.parse_log_line("") is None

    def test_level_must_be_uppercase(self) -> None:
        assert pl.parse_log_line("2024-01-01 12:00:00 info User 42 logged in") is None


class TestReadLogEntries:
    def test_reads_only_parseable_lines(self, tmp_path) -> None:
        log = tmp_path / "server.log"
        log.write_text(
            "2024-01-01 12:00:00 INFO User 42 logged in\n"
            "garbage line\n"
            "2024-01-01 12:05:00 ERROR Database timeout\n",
            encoding="utf-8",
        )
        entries = pl.read_log_entries(log)
        assert len(entries) == 2
        assert entries[0].message == "User 42 logged in"

    def test_missing_file_yields_no_entries(self, tmp_path) -> None:
        assert pl.read_log_entries(tmp_path / "absent.log") == []


class TestAggregateErrorCounts:
    def test_counts_duplicate_messages(self) -> None:
        entries = [
            make_entry("a", "ERROR", "Database timeout"),
            make_entry("b", "ERROR", "Database timeout"),
            make_entry("c", "ERROR", "Disk full"),
            make_entry("d", "INFO", "User 1 logged in"),
        ]
        assert pl.aggregate_error_counts(entries) == {
            "Database timeout": 2,
            "Disk full": 1,
        }


class TestExtractApiCalls:
    def test_parses_duration(self) -> None:
        entry = make_entry("t", "INFO", "API /users/profile took 250ms")
        assert pl.extract_api_calls([entry]) == [pl.ApiCall("/users/profile", 250)]

    def test_defaults_missing_duration_to_zero(self) -> None:
        entry = make_entry("t", "INFO", "API /health")
        assert pl.extract_api_calls([entry]) == [pl.ApiCall("/health", 0)]

    def test_ignores_non_api_lines(self) -> None:
        entry = make_entry("t", "INFO", "User 42 logged in")
        assert pl.extract_api_calls([entry]) == []


class TestComputeApiMetrics:
    def test_averages_per_endpoint(self) -> None:
        calls = [pl.ApiCall("/a", 100), pl.ApiCall("/a", 300), pl.ApiCall("/b", 50)]
        metrics = pl.compute_api_metrics(calls)
        assert {m.endpoint: m.avg_ms for m in metrics} == {"/a": 200.0, "/b": 50.0}


class TestCountActiveSessions:
    def test_login_logout_pair_ends_at_zero(self) -> None:
        entries = [
            make_entry("t1", "INFO", "User 42 logged in"),
            make_entry("t2", "INFO", "User 42 logged out"),
        ]
        assert pl.count_active_sessions(entries) == 0

    def test_user_stays_active_without_logout(self) -> None:
        assert pl.count_active_sessions([make_entry("t1", "INFO", "User 42 logged in")]) == 1

    def test_logout_without_login_is_ignored(self) -> None:
        assert pl.count_active_sessions([make_entry("t1", "INFO", "User 42 logged out")]) == 0

    def test_two_users_both_active(self) -> None:
        entries = [
            make_entry("t1", "INFO", "User 1 logged in"),
            make_entry("t2", "INFO", "User 2 logged in"),
        ]
        assert pl.count_active_sessions(entries) == 2


class TestRenderReport:
    def test_contains_expected_sections(self) -> None:
        report = pl.render_report(
            {"Database timeout": 2},
            [pl.ApiMetric("/users/profile", 250.0)],
            0,
        )
        assert "<b>Database timeout</b>: 2 occurrences" in report
        assert "<td>/users/profile</td>" in report
        assert "250.0" in report
        assert "0 user(s) currently active" in report

    def test_escapes_html_in_dynamic_content(self) -> None:
        report = pl.render_report(
            {"<script>alert(1)</script>": 1},
            [pl.ApiMetric("/a<b", 100.0)],
            2,
        )
        assert "<script>alert(1)</script>" not in report
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
        assert "&lt;b" in report  # endpoint escaped
