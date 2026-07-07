from hush_brain.brain import Brain, slugify


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("   ") == "memory"


def test_remember_creates_memory_and_index(tmp_path):
    brain = Brain(tmp_path)
    memory = brain.remember("The red pill", "Reality is a simulation run by machines.", tags=["matrix"])
    assert memory["slug"] == "the-red-pill"
    assert (tmp_path / "memories" / "the-red-pill.md").exists()
    index = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "[[the-red-pill]]" in index
    assert "[[the-red-pill]]" in brain.hot()


def test_duplicate_titles_get_unique_slugs(tmp_path):
    brain = Brain(tmp_path)
    first = brain.remember("Same title", "one")
    second = brain.remember("Same title", "two")
    assert first["slug"] != second["slug"]
    assert brain.stats()["memories"] == 2


def test_recall_ranks_title_matches_higher(tmp_path):
    brain = Brain(tmp_path)
    brain.remember("Kung fu training", "Neo learns kung fu through direct upload.")
    brain.remember("Ship maintenance", "The Nebuchadnezzar needs repairs, no kung involved.")
    hits = brain.recall("kung fu")
    assert hits
    assert hits[0]["slug"] == "kung-fu-training"


def test_recall_no_hits(tmp_path):
    brain = Brain(tmp_path)
    brain.remember("A fact", "something small")
    assert brain.recall("zion architecture") == []
    assert brain.recall("") == []


def test_hot_cache_is_capped(tmp_path):
    brain = Brain(tmp_path)
    for i in range(80):
        brain.remember(f"memory number {i}", "word " * 30)
    assert brain.stats()["hot_words"] <= 550  # cap plus header slack
