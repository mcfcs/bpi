from app import charts


def test_charts_skip_metrics_with_fewer_than_two_points(db, people):
    with db.as_user(people["ben"].id) as conn:
        points = charts.load_points(conn, {"barrier:app_errors", "barrier:fees"})
    assert charts.build_chart("barrier:app_errors", points["barrier:app_errors"]) is None
    assert charts.build_chart("barrier:fees", points["barrier:fees"]) is not None


def test_subgroups_replace_their_study_total_and_bars_are_sorted(db, people):
    with db.as_user(people["ben"].id) as conn:
        spec = charts.build_chart("barrier:fees", charts.load_points(conn, {"barrier:fees"})["barrier:fees"])
    labels = [b["label"] for b in spec["bars"]]
    assert labels[0] == "Ages 20–29" and "Ages 30–40" in labels
    assert not any(b["study_code"] == "SI-2026-014" and b["label"].startswith("Ages 20–40") for b in spec["bars"])
    values = [b["value"] for b in spec["bars"]]
    assert values == sorted(values, reverse=True)
    assert all(b["base_n"] and b["tier"] for b in spec["bars"])


def test_charts_respect_rls(db, people):
    with db.as_user(people["carla"].id) as conn:
        spec = charts.build_chart("barrier:fees", charts.load_points(conn, {"barrier:fees"})["barrier:fees"])
    assert all(b["study_code"] != "SI-2026-014" for b in spec["bars"])


def test_qualitative_studies_are_never_charted(db, people):
    with db.as_user(people["ana"].id) as conn:
        points = charts.load_points(conn, {"barrier:fees", "support:contact_person", "qr:cash_habit"})
    assert set(points) == {"barrier:fees"}
    assert all(p["study_code"] not in ("SI-2025-031", "SI-2026-033") for p in points["barrier:fees"])
