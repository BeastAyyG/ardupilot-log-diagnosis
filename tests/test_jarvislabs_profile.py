from pathlib import Path


ROOT = Path(__file__).parents[1]
OPS = ROOT / "ops" / "jarvis"


def test_jarvis_publish_is_native_x86_and_digest_pinned() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "publish-jarvislabs-image.yml"
    ).read_text(encoding="utf-8")
    assert "platforms: linux/amd64" in workflow
    assert "ARDUPILOT_COMMIT=${{ inputs.ardupilot_commit }}" in workflow
    assert "BASE_DIGEST=${{ inputs.base_digest }}" in workflow
    assert "provenance: mode=max" in workflow
    assert "sbom: true" in workflow
    assert "GHCR_IMAGE: ghcr.io/beastayyg/ardupilot-log-diagnosis" in workflow
    assert "ghcr.io/${{ github.repository_owner }}" not in workflow


def test_dstack_canary_is_privileged_cost_bounded_and_not_error_retried() -> None:
    config = (OPS / "sitl-canary.dstack.yml").read_text(encoding="utf-8")
    assert "privileged: true" in config
    assert "backends: [jarvislabs]" in config
    assert "on_events: [no-capacity, interruption]" in config
    assert "max_duration: 20m" in config
    assert "max_price: 0.10" in config
    assert "REPLACE_WITH_64_HEX_DIGEST" in config
    assert "error" not in config.split("on_events:", 1)[1].splitlines()[0]


def test_vm_bootstrap_requires_immutable_image_and_checks_architecture() -> None:
    script = (OPS / "bootstrap_vm.sh").read_text(encoding="utf-8")
    assert "@sha256:[0-9a-f]{64}" in script
    assert "--privileged --network none" in script
    assert '[[ "$image_arch" != "amd64" ]]' in script
    assert "user_network_namespace_ok" in script
    assert "GHCR_READ_TOKEN" in script
    assert "--password-stdin" in script


def test_sitl_container_pins_ardupilot_codegen_dependency() -> None:
    dockerfile = (
        ROOT / "synthetic_data" / "cluster" / "containers" / "Dockerfile.ardupilot-sitl"
    ).read_text(encoding="utf-8")
    assert "empy==3.3.4" in dockerfile
    assert "pexpect==4.9.0" in dockerfile


def test_training_profile_does_not_waste_a_gpu() -> None:
    config = (OPS / "training-cpu.dstack.yml").read_text(encoding="utf-8")
    assert "gpu:" not in config
    assert "cpu: x86:4" in config
    assert "max_price: 0.10" in config
