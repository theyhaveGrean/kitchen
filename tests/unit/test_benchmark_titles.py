from benchmarks.batch import titles_compatible


def test_title_comparison_allows_publisher_qualifiers():
    assert titles_compatible("Marry Me Chicken", "One-Pan Marry Me Chicken / Risoni Pasta")
    assert titles_compatible("Chicken Curry", "Easy Chicken Curry Recipe")


def test_title_comparison_rejects_unrelated_recipe():
    assert not titles_compatible("Chicken Curry", "Chocolate Brownies")
