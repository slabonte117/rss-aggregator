import unittest
from datetime import datetime, timedelta, timezone

import prune

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def row(rid, age_days, keep=False, with_keep=True):
    created = (NOW - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    props = {"Title": {"title": [{"plain_text": f"Row {rid}"}]}}
    if with_keep:
        props["Keep"] = {"type": "checkbox", "checkbox": keep}
    return {"id": rid, "created_time": created, "properties": props}


class FakeNotion:
    """Minimal stand-in: serves rows matching the same rule the real filter applies."""

    def __init__(self, rows):
        self.rows = {r["id"]: r for r in rows}
        self.archived = []
        self.queries = 0
        self.data_sources = self
        self.pages = self

    def query(self, data_source_id, filter, page_size, start_cursor=None):
        self.queries += 1
        cutoff = prune.parse_created(filter["and"][0]["created_time"]["before"])
        live = [r for r in self.rows.values()
                if r["id"] not in self.archived
                and prune.parse_created(r["created_time"]) < cutoff
                and not r["properties"]["Keep"]["checkbox"]]
        start = int(start_cursor or 0)
        page = live[start:start + page_size]
        more = start + page_size < len(live)
        return {"results": page, "has_more": more, "next_cursor": str(start + page_size)}

    def update(self, page_id, archived):
        assert archived is True
        self.archived.append(page_id)


class ShouldPruneTests(unittest.TestCase):
    cutoff = NOW - timedelta(days=30)

    def test_old_unkept_is_pruned(self):
        self.assertTrue(prune.should_prune(row("a", 31), self.cutoff))

    def test_recent_is_kept(self):
        self.assertFalse(prune.should_prune(row("a", 5), self.cutoff))

    def test_keep_checked_is_never_pruned(self):
        self.assertFalse(prune.should_prune(row("a", 400, keep=True), self.cutoff))

    def test_missing_keep_property_aborts(self):
        with self.assertRaises(prune.PruneAbort):
            prune.should_prune(row("a", 400, with_keep=False), self.cutoff)


class RunPruneTests(unittest.TestCase):
    def setUp(self):
        for k in ("PRUNE_ENABLED", "PRUNE_AFTER_DAYS", "PRUNE_MAX_PER_RUN",
                  "PRUNE_TIME_BUDGET_SECONDS", "PRUNE_DRY_RUN"):
            prune.os.environ.pop(k, None)

    def make(self):
        rows = [row(f"old{i}", 40 + i) for i in range(5)]
        rows += [row("kept", 90, keep=True), row("new1", 2), row("new2", 29)]
        return FakeNotion(rows)

    def test_prunes_only_old_unkept(self):
        n = self.make()
        out = prune.run_prune(n, "ds", now=NOW, sleep=lambda s: None)
        self.assertEqual(out["pruned"], 5)
        self.assertEqual(sorted(n.archived), [f"old{i}" for i in range(5)])

    def test_dry_run_changes_nothing(self):
        prune.os.environ["PRUNE_DRY_RUN"] = "1"
        n = self.make()
        out = prune.run_prune(n, "ds", now=NOW, sleep=lambda s: None)
        self.assertEqual(out["candidates"], 5)
        self.assertEqual(n.archived, [])

    def test_cap_limits_a_run(self):
        prune.os.environ["PRUNE_MAX_PER_RUN"] = "2"
        n = self.make()
        out = prune.run_prune(n, "ds", now=NOW, sleep=lambda s: None)
        self.assertEqual(out["pruned"], 2)
        self.assertEqual(len(n.archived), 2)

    def test_disabled(self):
        prune.os.environ["PRUNE_ENABLED"] = "0"
        n = self.make()
        out = prune.run_prune(n, "ds", now=NOW, sleep=lambda s: None)
        self.assertEqual(out["pruned"], 0)
        self.assertEqual(n.queries, 0)

    def test_second_run_finishes_backlog(self):
        prune.os.environ["PRUNE_MAX_PER_RUN"] = "3"
        n = self.make()
        prune.run_prune(n, "ds", now=NOW, sleep=lambda s: None)
        prune.run_prune(n, "ds", now=NOW, sleep=lambda s: None)
        self.assertEqual(len(n.archived), 5)


if __name__ == "__main__":
    unittest.main()
