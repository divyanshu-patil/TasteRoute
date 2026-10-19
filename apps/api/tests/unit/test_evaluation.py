from tasteroute_api.evaluation import a_wins, blind_pairs, jaccard, spearman


def test_jaccard_and_spearman():
    assert jaccard(["a", "b", "c"], ["b", "c", "d"]) == 0.5
    assert jaccard([], []) == 0.0
    assert spearman(["a", "b", "c", "x"], ["a", "b", "c"]) == 1.0
    assert spearman(["a", "b", "c"], ["c", "b", "a"]) == -1.0
    assert spearman(["a", "b"], ["a", "b"]) is None


def test_blind_pairs_hide_the_side_and_score():
    a = [{"name": f"A{i}"} for i in range(12)]
    c = [{"name": f"C{i}"} for i in range(8)]
    rows = blind_pairs(a, c, 10, seed=7)
    assert len(rows) == 8
    assert {r["a_is"] for r in rows} == {1, 2}  # both sides used
    for r in rows:
        shown_a = r["venue_1"] if r["a_is"] == 1 else r["venue_2"]
        assert shown_a["name"].startswith("A")
    assert blind_pairs(a, c, 10, seed=7) == rows  # reproducible
    key = {r["pair"]: r["a_is"] for r in rows}
    assert a_wins({1: key[1], 2: 3 - key[2], 3: 0}, key) == (1, 2)
