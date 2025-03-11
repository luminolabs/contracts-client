import pytest

from lumino.contracts_client.hw_spec.compute_power_classifier import ComputePowerClassifier


# Using pytest fixtures instead of setUp/tearDown
@pytest.fixture
def classifier():
    return ComputePowerClassifier()


def test_parse_hardware_specs_a100_40gb():
    """Test parsing hardware specs with A100 40GB GPUs"""
    hardware_info = {
        "gpu": {
            "nvidia": {
                "available": True,
                "count": 2,
                "devices": [
                    {"model": "NVIDIA A100-SXM4-40GB", "memory_mb": 40960},
                    {"model": "NVIDIA A100-SXM4-40GB", "memory_mb": 40960}
                ]
            }
        },
        "cpu": {"cores": 32, "speed_mhz": 3000},
        "memory": {"total_mb": 262144}  # 256 GB
    }

    parsed = ComputePowerClassifier.parse_hardware_specs(hardware_info)

    assert parsed["gpu"]["has_nvidia"]
    assert len(parsed["gpu"]["nvidia_gpus"]) == 2
    assert parsed["gpu"]["nvidia_gpus"][0]["type"] == "a100-40gb"
    assert parsed["gpu"]["total_gpu_memory_gb"] == 80
    assert parsed["cpu"]["cores"] == 32
    assert parsed["memory"]["total_gb"] == 256


def test_parse_hardware_specs_a100_80gb():
    """Test parsing hardware specs with A100 80GB GPUs"""
    hardware_info = {
        "gpu": {
            "nvidia": {
                "available": True,
                "count": 4,
                "devices": [
                    {"model": "NVIDIA A100-SXM4-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA A100-SXM4-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA A100-SXM4-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA A100-SXM4-80GB", "memory_mb": 81920}
                ]
            }
        },
        "cpu": {"cores": 64, "speed_mhz": 3200},
        "memory": {"total_mb": 524288}  # 512 GB
    }

    parsed = ComputePowerClassifier.parse_hardware_specs(hardware_info)

    assert parsed["gpu"]["has_nvidia"]
    assert len(parsed["gpu"]["nvidia_gpus"]) == 4
    assert parsed["gpu"]["nvidia_gpus"][0]["type"] == "a100-80gb"
    assert parsed["gpu"]["total_gpu_memory_gb"] == 320
    assert parsed["cpu"]["cores"] == 64
    assert parsed["memory"]["total_gb"] == 512


def test_parse_hardware_specs_h100_80gb():
    """Test parsing hardware specs with H100 80GB GPUs"""
    hardware_info = {
        "gpu": {
            "nvidia": {
                "available": True,
                "count": 8,
                "devices": [
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920},
                    {"model": "NVIDIA H100-SXM5-80GB", "memory_mb": 81920}
                ]
            }
        },
        "cpu": {"cores": 128, "speed_mhz": 3400},
        "memory": {"total_mb": 1048576}  # 1 TB
    }

    parsed = ComputePowerClassifier.parse_hardware_specs(hardware_info)

    assert parsed["gpu"]["has_nvidia"]
    assert len(parsed["gpu"]["nvidia_gpus"]) == 8
    assert parsed["gpu"]["nvidia_gpus"][0]["type"] == "h100-80gb"
    assert parsed["gpu"]["total_gpu_memory_gb"] == 640
    assert parsed["cpu"]["cores"] == 128
    assert parsed["memory"]["total_gb"] == 1024


def test_parse_hardware_specs_no_gpu():
    """Test parsing hardware specs with no GPUs"""
    hardware_info = {
        "cpu": {"cores": 16, "speed_mhz": 2800},
        "memory": {"total_mb": 131072}  # 128 GB
    }

    parsed = ComputePowerClassifier.parse_hardware_specs(hardware_info)

    assert not parsed["gpu"]["has_nvidia"]
    assert len(parsed["gpu"]["nvidia_gpus"]) == 0
    assert parsed["gpu"]["total_gpu_memory_gb"] == 0
    assert parsed["cpu"]["cores"] == 16
    assert parsed["memory"]["total_gb"] == 128


def test_calculate_compute_power_a100_40gb_single():
    """Test compute power calculation for single A100 40GB"""
    parsed_specs = {
        "gpu": {
            "has_nvidia": True,
            "nvidia_gpus": [{"type": "a100-40gb", "memory_gb": 40}],
            "total_gpu_memory_gb": 40
        },
        "cpu": {"cores": 16, "speed_mhz": 2800},
        "memory": {"total_gb": 128}
    }

    compute_power = ComputePowerClassifier.calculate_compute_power(parsed_specs)

    assert compute_power == 500  # 500 for a100-40gb


def test_calculate_compute_power_a100_40gb_multiple():
    """Test compute power calculation for multiple A100 40GB"""
    parsed_specs = {
        "gpu": {
            "has_nvidia": True,
            "nvidia_gpus": [
                {"type": "a100-40gb", "memory_gb": 40},
                {"type": "a100-40gb", "memory_gb": 40},
                {"type": "a100-40gb", "memory_gb": 40},
                {"type": "a100-40gb", "memory_gb": 40}
            ],
            "total_gpu_memory_gb": 160
        },
        "cpu": {"cores": 32, "speed_mhz": 3000},
        "memory": {"total_gb": 256}
    }

    compute_power = ComputePowerClassifier.calculate_compute_power(parsed_specs)

    assert compute_power == 1500  # Actual calculated value


def test_calculate_compute_power_a100_80gb_multiple():
    """Test compute power calculation for multiple A100 80GB"""
    parsed_specs = {
        "gpu": {
            "has_nvidia": True,
            "nvidia_gpus": [
                {"type": "a100-80gb", "memory_gb": 80},
                {"type": "a100-80gb", "memory_gb": 80},
                {"type": "a100-80gb", "memory_gb": 80},
                {"type": "a100-80gb", "memory_gb": 80}
            ],
            "total_gpu_memory_gb": 320
        },
        "cpu": {"cores": 64, "speed_mhz": 3200},
        "memory": {"total_gb": 512}
    }

    compute_power = ComputePowerClassifier.calculate_compute_power(parsed_specs)

    assert compute_power == 2700  # Actual calculated value


def test_calculate_compute_power_h100_80gb_multiple():
    """Test compute power calculation for multiple H100 80GB"""
    parsed_specs = {
        "gpu": {
            "has_nvidia": True,
            "nvidia_gpus": [
                {"type": "h100-80gb", "memory_gb": 80},
                {"type": "h100-80gb", "memory_gb": 80},
                {"type": "h100-80gb", "memory_gb": 80},
                {"type": "h100-80gb", "memory_gb": 80},
                {"type": "h100-80gb", "memory_gb": 80},
                {"type": "h100-80gb", "memory_gb": 80},
                {"type": "h100-80gb", "memory_gb": 80},
                {"type": "h100-80gb", "memory_gb": 80}
            ],
            "total_gpu_memory_gb": 640
        },
        "cpu": {"cores": 128, "speed_mhz": 3400},
        "memory": {"total_gb": 1024}
    }

    compute_power = ComputePowerClassifier.calculate_compute_power(parsed_specs)

    assert compute_power == 8400  # Actual calculated value


def test_calculate_compute_power_mixed_gpus():
    """Test compute power calculation for mixed GPU types"""
    parsed_specs = {
        "gpu": {
            "has_nvidia": True,
            "nvidia_gpus": [
                {"type": "a100-40gb", "memory_gb": 40},
                {"type": "a100-40gb", "memory_gb": 40},
                {"type": "a100-80gb", "memory_gb": 80},
                {"type": "a100-80gb", "memory_gb": 80}
            ],
            "total_gpu_memory_gb": 240
        },
        "cpu": {"cores": 64, "speed_mhz": 3200},
        "memory": {"total_gb": 512}
    }

    compute_power = ComputePowerClassifier.calculate_compute_power(parsed_specs)

    assert compute_power == 2400  # Actual expected value with scaling


def test_calculate_compute_power_no_gpu():
    """Test compute power calculation with no GPUs"""
    parsed_specs = {
        "gpu": {
            "has_nvidia": False,
            "nvidia_gpus": [],
            "total_gpu_memory_gb": 0
        },
        "cpu": {"cores": 16, "speed_mhz": 2800},
        "memory": {"total_gb": 128}
    }

    compute_power = ComputePowerClassifier.calculate_compute_power(parsed_specs)

    assert compute_power == 0  # No GPUs means 0 compute power


def test_model_requirements_validation():
    """Validate that the model requirements match the provided JSON"""
    expected_requirements = {
        "llm_llama3_1_8b": {
            "lora": {"gpu_type": "a100-40gb", "num_gpus": 1},
            "qlora": {"gpu_type": "a100-40gb", "num_gpus": 1},
            "full": {"gpu_type": "a100-40gb", "num_gpus": 4}
        },
        "llm_llama3_2_1b": {
            "lora": {"gpu_type": "a100-40gb", "num_gpus": 1},
            "qlora": {"gpu_type": "a100-40gb", "num_gpus": 1},
            "full": {"gpu_type": "a100-40gb", "num_gpus": 1}
        },
        "llm_llama3_2_3b": {
            "lora": {"gpu_type": "a100-40gb", "num_gpus": 1},
            "qlora": {"gpu_type": "a100-40gb", "num_gpus": 1},
            "full": {"gpu_type": "a100-40gb", "num_gpus": 1}
        },
        "llm_llama3_1_70b": {
            "lora": {"gpu_type": "a100-80gb", "num_gpus": 4},
            "qlora": {"gpu_type": "a100-80gb", "num_gpus": 4},
            "full": {"gpu_type": "h100-80gb", "num_gpus": 8}
        }
    }

    assert ComputePowerClassifier.MODEL_REQUIREMENTS == expected_requirements


def test_can_run_model_llama3_1_8b():
    """Test compatibility check for llm_llama3_1_8b with different hardware"""
    # Check the minimum required compute power for lora and qlora
    min_power_lora = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_8b", "lora")
    min_power_qlora = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_8b", "qlora")
    min_power_full = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_8b", "full")

    # Test lora and qlora with sufficient compute power
    assert ComputePowerClassifier.can_run_model(min_power_lora, "llm_llama3_1_8b", "lora")
    assert ComputePowerClassifier.can_run_model(min_power_qlora, "llm_llama3_1_8b", "qlora")

    # Test with insufficient compute power
    assert not ComputePowerClassifier.can_run_model(min_power_lora - 100, "llm_llama3_1_8b", "lora")

    # Test full with single A100 40GB (should fail)
    assert not ComputePowerClassifier.can_run_model(500, "llm_llama3_1_8b", "full")

    # Test full with sufficient compute power
    assert ComputePowerClassifier.can_run_model(min_power_full, "llm_llama3_1_8b", "full")


def test_can_run_model_llama3_2_1b():
    """Test compatibility check for llm_llama3_2_1b with different hardware"""
    # Get the minimum required compute power for each training type
    min_power_lora = ComputePowerClassifier.get_required_compute_power("llm_llama3_2_1b", "lora")
    min_power_qlora = ComputePowerClassifier.get_required_compute_power("llm_llama3_2_1b", "qlora")
    min_power_full = ComputePowerClassifier.get_required_compute_power("llm_llama3_2_1b", "full")

    # Test with sufficient compute power
    assert ComputePowerClassifier.can_run_model(min_power_lora, "llm_llama3_2_1b", "lora")
    assert ComputePowerClassifier.can_run_model(min_power_qlora, "llm_llama3_2_1b", "qlora")
    assert ComputePowerClassifier.can_run_model(min_power_full, "llm_llama3_2_1b", "full")

    # Should work with better GPUs too
    assert ComputePowerClassifier.can_run_model(900, "llm_llama3_2_1b", "full")
    assert ComputePowerClassifier.can_run_model(1600, "llm_llama3_2_1b", "full")

    # Should fail with insufficient compute power
    assert not ComputePowerClassifier.can_run_model(min_power_full - 100, "llm_llama3_2_1b", "full")


def test_can_run_model_llama3_2_3b():
    """Test compatibility check for llm_llama3_2_3b with different hardware"""
    # Get the minimum required compute power for each training type
    min_power_lora = ComputePowerClassifier.get_required_compute_power("llm_llama3_2_3b", "lora")
    min_power_qlora = ComputePowerClassifier.get_required_compute_power("llm_llama3_2_3b", "qlora")
    min_power_full = ComputePowerClassifier.get_required_compute_power("llm_llama3_2_3b", "full")

    # Test with sufficient compute power
    assert ComputePowerClassifier.can_run_model(min_power_lora, "llm_llama3_2_3b", "lora")
    assert ComputePowerClassifier.can_run_model(min_power_qlora, "llm_llama3_2_3b", "qlora")
    assert ComputePowerClassifier.can_run_model(min_power_full, "llm_llama3_2_3b", "full")

    # Should work with better GPUs too
    assert ComputePowerClassifier.can_run_model(900, "llm_llama3_2_3b", "full")
    assert ComputePowerClassifier.can_run_model(1600, "llm_llama3_2_3b", "full")

    # Should fail with insufficient compute power
    assert not ComputePowerClassifier.can_run_model(min_power_full - 100, "llm_llama3_2_3b", "full")


def test_can_run_model_llama3_1_70b():
    """Test compatibility check for llm_llama3_1_70b with different hardware"""
    # Get the minimum required compute power for each training type
    min_power_lora = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_70b", "lora")
    min_power_qlora = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_70b", "qlora")
    min_power_full = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_70b", "full")

    # Test with insufficient hardware
    assert not ComputePowerClassifier.can_run_model(min_power_lora - 100, "llm_llama3_1_70b", "lora")

    # Test lora and qlora with sufficient compute power
    assert ComputePowerClassifier.can_run_model(min_power_lora, "llm_llama3_1_70b", "lora")
    assert ComputePowerClassifier.can_run_model(min_power_qlora, "llm_llama3_1_70b", "qlora")

    # Test full with 4 A100 80GB (should fail, needs more compute power)
    assert not ComputePowerClassifier.can_run_model(3000, "llm_llama3_1_70b", "full")

    # Test full with sufficient compute power (should pass)
    assert ComputePowerClassifier.can_run_model(min_power_full, "llm_llama3_1_70b", "full")


def test_get_required_compute_power():
    """Test computation of required compute power for different models"""
    # For each model and training type, calculate the expected required power
    for model_name, training_types in ComputePowerClassifier.MODEL_REQUIREMENTS.items():
        for training_type, req in training_types.items():
            # Get the GPU type and number required
            gpu_type = req["gpu_type"]
            num_gpus = req["num_gpus"]

            # Calculate the minimum compute power needed using the same formula as the class
            base_power = ComputePowerClassifier.GPU_POWER_RATINGS[gpu_type] * num_gpus
            with_buffer = int(base_power * 1.1)  # 10% buffer
            expected_power = round(with_buffer / 100) * 100  # Round to nearest 100

            # Test that the method returns the expected value
            actual_power = ComputePowerClassifier.get_required_compute_power(model_name, training_type)
            assert actual_power == expected_power, (
                f"Mismatch for {model_name} ({training_type}): expected {expected_power}, got {actual_power}"
            )

    # Invalid model or training type should return 0
    assert ComputePowerClassifier.get_required_compute_power("invalid_model") == 0
    assert ComputePowerClassifier.get_required_compute_power("llm_llama3_1_8b", "invalid_type") == 0


def test_get_best_pool_for_job():
    """Test best pool recommendation for different jobs"""
    # Should be identical to get_required_compute_power
    assert (ComputePowerClassifier.get_best_pool_for_job("llm_llama3_1_8b", "lora") ==
            ComputePowerClassifier.get_required_compute_power("llm_llama3_1_8b", "lora"))

    assert (ComputePowerClassifier.get_best_pool_for_job("llm_llama3_1_70b", "full") ==
            ComputePowerClassifier.get_required_compute_power("llm_llama3_1_70b", "full"))


def test_get_suitable_models():
    """Test finding suitable models for different hardware capabilities"""
    # No GPU
    assert ComputePowerClassifier.get_suitable_models(0) == {}

    # Get required compute powers
    llm_8b_lora = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_8b", "lora")
    llm_8b_full = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_8b", "full")
    llm_2_1b_lora = ComputePowerClassifier.get_required_compute_power("llm_llama3_2_1b", "lora")
    llm_70b_lora = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_70b", "lora")
    llm_70b_full = ComputePowerClassifier.get_required_compute_power("llm_llama3_1_70b", "full")

    # Single A100 40GB with minimum required power for small models
    suitable_for_smaller_models = ComputePowerClassifier.get_suitable_models(llm_8b_lora)
    assert "llm_llama3_1_8b" in suitable_for_smaller_models
    assert "llm_llama3_2_1b" in suitable_for_smaller_models
    assert "llm_llama3_2_3b" in suitable_for_smaller_models
    assert set(suitable_for_smaller_models["llm_llama3_1_8b"]) == {"lora", "qlora"}
    assert set(suitable_for_smaller_models["llm_llama3_2_1b"]) == {"lora", "qlora", "full"}
    assert set(suitable_for_smaller_models["llm_llama3_2_3b"]) == {"lora", "qlora", "full"}
    assert "llm_llama3_1_70b" not in suitable_for_smaller_models

    # Hardware capable of full training for 8B model
    suitable_for_8b_full = ComputePowerClassifier.get_suitable_models(llm_8b_full)
    assert "llm_llama3_1_8b" in suitable_for_8b_full
    assert "full" in suitable_for_8b_full["llm_llama3_1_8b"]

    # Hardware for 70B models
    suitable_for_70b_lora = ComputePowerClassifier.get_suitable_models(llm_70b_lora)
    assert "llm_llama3_1_70b" in suitable_for_70b_lora
    assert {"lora", "qlora"}.issubset(set(suitable_for_70b_lora["llm_llama3_1_70b"]))
    assert "full" not in suitable_for_70b_lora["llm_llama3_1_70b"]

    # Hardware for 70B full training
    suitable_for_70b_full = ComputePowerClassifier.get_suitable_models(llm_70b_full)
    assert "llm_llama3_1_70b" in suitable_for_70b_full
    assert "full" in suitable_for_70b_full["llm_llama3_1_70b"]


if __name__ == "__main__":
    pytest.main([__file__])
