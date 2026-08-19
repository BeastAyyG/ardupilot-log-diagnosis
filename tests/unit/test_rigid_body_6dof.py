import numpy as np

from src.core.physics.rigid_body_6dof import solve_rigid_body_6dof


def test_rigid_body_residuals_use_body_frame_ned_gravity():
    result = solve_rigid_body_6dof(
        [[10.0, 0.0, 9.80665], [10.0, 0.0, 9.80665]],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        mass_kg=2.0,
        inertia_kg_m2=np.eye(3),
        gravity_body=[0.0, 0.0, 9.80665],
    )

    assert np.allclose(result.measured_force_body, [[20.0, 0.0, 0.0]] * 2)
    assert np.allclose(result.residual_force_body, [[20.0, 0.0, 0.0]] * 2)
    assert np.allclose(result.expected_torque_body, 0.0)
    assert np.allclose(result.residual_torque_body, [[1.0, 0.0, 0.0]] * 2)
