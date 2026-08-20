from __future__ import annotations

from training.corel_operator.pilot import select_mutation_pilot_rows


def test_mutation_pilot_selects_only_eligible_text_documents() -> None:
    inventory = {
        "file:one": {"file_id": "file:one", "absolute_path": "one.cdr"},
        "file:two": {"file_id": "file:two", "absolute_path": "two.cdr"},
        "file:three": {"file_id": "file:three", "absolute_path": "three.cdr"},
    }
    census = [
        {
            "file_id": "file:one",
            "result": {"operator_eligible": True, "counts": {"text": 2}},
        },
        {
            "file_id": "file:two",
            "result": {"operator_eligible": False, "counts": {"text": 3}},
        },
        {
            "file_id": "file:three",
            "result": {"operator_eligible": True, "counts": {"text": 0}},
        },
    ]
    selected = select_mutation_pilot_rows(census, inventory, limit=20)
    assert selected == [inventory["file:one"]]


def test_mutation_pilot_selection_is_deterministic() -> None:
    inventory = {
        f"file:{index}": {
            "file_id": f"file:{index}",
            "absolute_path": f"{index}.cdr",
        }
        for index in range(10)
    }
    census = [
        {
            "file_id": file_id,
            "result": {"operator_eligible": True, "counts": {"text": 1}},
        }
        for file_id in inventory
    ]
    first = select_mutation_pilot_rows(census, inventory, limit=5, seed="fixed")
    second = select_mutation_pilot_rows(
        list(reversed(census)), inventory, limit=5, seed="fixed"
    )
    assert [row["file_id"] for row in first] == [row["file_id"] for row in second]
    assert len(first) == 5
