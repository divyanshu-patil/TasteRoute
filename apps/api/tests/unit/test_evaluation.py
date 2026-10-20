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


def test_stockist_metrics():
    """EVL-04: recall@k, mean percentile rank (first 100, last 0), long tail, a fixed shuffle."""
    from tasteroute_api.evaluation import hash_order, long_tail, mean_percentile_rank, recall_at_k

    ranked = ["a", "b", "c", "d", "e"]
    assert recall_at_k(ranked, {"a", "e"}, 2) == 0.5 and recall_at_k(ranked, set(), 2) is None
    assert mean_percentile_rank(ranked, {"a"}) == 100 and mean_percentile_rank(ranked, {"e"}) == 0
    assert mean_percentile_rank(ranked, {"a", "e", "zz"}) == 50
    assert long_tail({"a", "e"}, ["a", "b"]) == {"e"}
    assert hash_order(ranked, "x") == hash_order(list(reversed(ranked)), "x") != hash_order(ranked, "y")
