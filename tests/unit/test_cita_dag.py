from src.core.causality.cita_dag import build_cita_dag


def test_cita_dag_orders_preimpact_root_cause():
    result = build_cita_dag(
        {
            "vibration": {"onset_us": 1_000_000, "score": 0.9},
            "ekf": {"onset_us": 3_000_000, "score": 0.7},
            "impact": {"onset_us": 4_000_000, "score": 1.0},
        },
        dependencies=[("vibration", "ekf"), ("ekf", "impact")],
        impact_boundary_us=4_000_000,
    )

    assert result.nodes == ("vibration", "ekf")
    assert result.edges == (("vibration", "ekf"),)
    assert result.topological_order == ("vibration", "ekf")
    assert result.root_cause == "vibration"
