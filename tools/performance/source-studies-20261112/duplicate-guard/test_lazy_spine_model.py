import unittest
from lazy_spine_model import (Session, Thunk, Bottom, source_list, walk, closure,
                              poison, finite_group_protocols)


def count(session, kind):
    return sum(event[0] == kind for event in session.events)


def without_repeat(events):
    return [event for event in events if event[0] != "repeat-closure"]


class LazySpineTests(unittest.TestCase):
    def test_construction_without_observation_is_lazy(self):
        for variant in ("original", "delete", "spine"):
            s = Session((("bottom",),), variant)
            self.assertEqual(s.observe("none"), "unobserved")
            self.assertEqual(s.events, [])

    def test_spine_candidate_matches_original_nonrepeat_events(self):
        for groups in ((), ((),), (("closed",),), ((), ("closed", "closed"), (), ("closed",))):
            old, new = Session(groups, "original"), Session(groups, "spine")
            for observation in ("either-whnf", "fragment-whnf", "head-pair", "full-spine"):
                self.assertEqual(old.observe(observation), new.observe(observation))
                self.assertEqual(without_repeat(old.events), new.events)

    def test_either_whnf_and_fragment_whnf_are_distinct(self):
        s = Session((("closed",),), "spine")
        self.assertEqual(s.observe("either-whnf"), "right-whnf")
        self.assertNotIn(("force", "fragment"), s.events)
        s.observe("fragment-whnf")
        self.assertIn(("force", "fragment"), s.events)

    def test_delete_defers_flattening_until_consumer_demand(self):
        groups = (("closed",) * 3,) * 4
        old, delete, spine = [Session(groups, v) for v in ("original", "delete", "spine")]
        for s in (old, delete, spine):
            s.observe("either-whnf")
        self.assertEqual([count(s, "flatten-cons") for s in (old, delete, spine)], [12, 0, 12])
        delete.observe("fragment-whnf")
        self.assertEqual(count(delete, "flatten-cons"), 0)
        delete.observe("owned-whnf")
        self.assertEqual(count(delete, "flatten-cons"), 1)
        delete.observe("head-pair")
        self.assertEqual(count(delete, "flatten-cons"), 1)
        delete.observe("full-spine")
        self.assertEqual(count(delete, "flatten-cons"), 12)

    def test_seq_owned_control_does_not_force_full_spine(self):
        weak = Session((("closed",) * 4,), "whnf-only")
        weak.observe("either-whnf")
        self.assertEqual(count(weak, "flatten-cons"), 1)
        weak.observe("full-spine")
        self.assertEqual(count(weak, "flatten-cons"), 4)

    def test_first_admission_already_forces_shared_entry_pairs(self):
        for variant in ("original", "delete", "spine"):
            s = Session((("closed", "closed"),), variant)
            s.observe("either-whnf")
            before = [e for e in s.events if e[0] == "force" and e[1].startswith("pair:")]
            self.assertEqual(len(before), 2)
            s.observe("head-pair")
            after = [e for e in s.events if e[0] == "force" and e[1].startswith("pair:")]
            self.assertEqual(before, after)

    def test_shared_flattened_spine_is_not_rebuilt(self):
        s = Session((("closed",) * 8,), "spine")
        s.observe("either-whnf")
        before = count(s, "flatten-cons")
        s.observe("full-spine")
        s.observe("full-spine")
        self.assertEqual(count(s, "flatten-cons"), before)

    def test_name_payload_can_remain_partial_after_all_spine_forcing(self):
        for variant in ("original", "delete", "spine"):
            s = Session((("closed",),), variant, bad_name=True)
            self.assertEqual(s.observe("full-spine"), "full-spine")
            self.assertNotIn(("force", "name:0:0"), s.events)
            self.assertEqual(s.observe("head-name"), ("modeled-bottom", "name:0:0"))

    def test_bad_source_chunk_tail_is_not_hidden_by_variant(self):
        for variant in ("original", "delete", "spine"):
            s = Session((("closed",),), variant, bad_source_tail=0)
            self.assertEqual(s.observe("either-whnf"), ("modeled-bottom", "chunk:0:tail"))
            self.assertEqual(count(s, "flatten-cons"), 0)

    def test_spine_only_does_not_validate_unadmitted_bad_head(self):
        events = []
        head = Thunk("unadmitted-head", lambda: poison("head"), events)
        raw = source_list([head], "raw", events)
        self.assertTrue(walk(raw))
        self.assertNotIn(("force", "unadmitted-head"), events)
        with self.assertRaises(Bottom):
            walk(raw, lambda h: closure(h, "closure", events))

    def test_partial_raw_tail_requires_more_than_whnf(self):
        events = []
        head = Thunk("head", lambda: ("x", None, "closed"), events)
        raw = source_list([head], "raw", events, bad_tail=True)
        raw.force()  # One constructor is available, but the tail is still bad.
        with self.assertRaises(Bottom):
            walk(raw)

    def test_259_group_protocols_preserve_results(self):
        number = 0
        for groups in finite_group_protocols():
            sessions = [Session(groups, v) for v in ("original", "delete", "spine")]
            for observation in ("either-whnf", "fragment-whnf", "head-pair", "full-spine"):
                values = [s.observe(observation) for s in sessions]
                self.assertEqual(values[0], values[1])
                self.assertEqual(values[0], values[2])
            self.assertEqual(without_repeat(sessions[0].events), sessions[2].events)
            number += 1
        self.assertEqual(number, 259)


if __name__ == "__main__":
    unittest.main(verbosity=2)
