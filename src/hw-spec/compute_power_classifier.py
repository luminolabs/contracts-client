#!/usr/bin/env python3

import json
import re
from typing import Dict, List, Optional, Union, Tuple

class ComputePowerClassifier:
    """
    Classifies node hardware and calculates computePower for job allocation.
    computePower is the normalized capability score that determines job assignment.
    Higher computePower values indicate more capable hardware.
    """

    # GPU Power Ratings (base values in 100s)
    GPU_POWER_RATINGS = {
        "a100-40gb": 500,   # A100 40GB
        "a100-80gb": 900,   # A100 80GB
        "h100-80gb": 1600,  # H100 80GB
    }

    # Model requirements (maps model names to their GPU requirements per training type)
    MODEL_REQUIREMENTS = {
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

    def __init__(self):
        """Initialize the compute power classifier."""
        pass

    @classmethod
    def parse_hardware_specs(cls, hardware_info: Dict) -> Dict:
        """
        Parse hardware specifications from HardwareInfo output.
        Returns a normalized representation of the hardware.
        """
        parsed = {
            "gpu": {
                "has_nvidia": False,
                "nvidia_gpus": [],
                "total_gpu_memory_gb": 0
            },
            "cpu": {
                "cores": 0,
                "speed_mhz": 0
            },
            "memory": {
                "total_gb": 0
            }
        }

        # Parse NVIDIA GPU information
        if "gpu" in hardware_info and "nvidia" in hardware_info["gpu"]:
            nvidia_info = hardware_info["gpu"]["nvidia"]
            if nvidia_info.get("available", False) and nvidia_info.get("count", 0) > 0:
                parsed["gpu"]["has_nvidia"] = True
                
                # Process each GPU device
                for device in nvidia_info.get("devices", []):
                    # Extract GPU model and memory
                    gpu_model = device.get("model", "").lower()
                    gpu_memory_mb = device.get("memory_mb", 0)
                    gpu_memory_gb = int(gpu_memory_mb / 1024) if gpu_memory_mb else 0

                    # Identify if this is an A100 or H100
                    gpu_type = None
                    if "a100" in gpu_model:
                        # Determine memory size
                        if gpu_memory_gb <= 45:  # Allowing some variation in reported size
                            gpu_type = "a100-40gb"
                        else:
                            gpu_type = "a100-80gb"
                    elif "h100" in gpu_model:
                        gpu_type = "h100-80gb"
                    
                    if gpu_type:
                        parsed["gpu"]["nvidia_gpus"].append({
                            "type": gpu_type,
                            "memory_gb": gpu_memory_gb
                        })
                        parsed["gpu"]["total_gpu_memory_gb"] += gpu_memory_gb

        # Parse CPU information
        if "cpu" in hardware_info:
            parsed["cpu"]["cores"] = hardware_info["cpu"].get("cores", 0)
            parsed["cpu"]["speed_mhz"] = hardware_info["cpu"].get("speed_mhz", 0)

        # Parse memory information
        if "memory" in hardware_info:
            mem_mb = hardware_info["memory"].get("total_mb", 0)
            parsed["memory"]["total_gb"] = int(mem_mb / 1024) if mem_mb else 0

        return parsed

    @classmethod
    def calculate_compute_power(cls, parsed_specs: Dict) -> int:
        """
        Calculate the computePower value based on parsed hardware specs.
        Returns an integer score in multiples of 100.
        """
        # Base power starts at 0
        compute_power = 0

        # If no NVIDIA GPUs or unsupported types, return 0
        if not parsed_specs["gpu"]["has_nvidia"] or not parsed_specs["gpu"]["nvidia_gpus"]:
            return 0

        # Count GPUs by type
        gpu_counts = {}
        for gpu in parsed_specs["gpu"]["nvidia_gpus"]:
            gpu_type = gpu["type"]
            if gpu_type in cls.GPU_POWER_RATINGS:
                gpu_counts[gpu_type] = gpu_counts.get(gpu_type, 0) + 1

        # Calculate power based on GPU counts and their ratings
        for gpu_type, count in gpu_counts.items():
            # Basic power contribution: rating × count
            power_contribution = cls.GPU_POWER_RATINGS[gpu_type] * count
            
            # Apply diminishing returns for multiple GPUs (sqrt scaling)
            # This reflects that 2 GPUs aren't exactly 2x as useful as 1 due to communication overhead
            scaling_factor = 1.0
            if count > 1:
                # Apply a scaling factor but still ensure more GPUs give more power
                scaling_factor = (count ** 0.8) / count  # Diminishing returns with more GPUs
            
            # Add this GPU type's contribution to the total compute power
            compute_power += int(power_contribution * scaling_factor)

        # Round to nearest 100
        compute_power = round(compute_power / 100) * 100
        
        return compute_power

    @classmethod
    def can_run_model(cls, compute_power: int, model_name: str, training_type: str = "lora") -> bool:
        """
        Determine if a node with the given computePower can run a specific model and training type.
        """
        if model_name not in cls.MODEL_REQUIREMENTS or training_type not in cls.MODEL_REQUIREMENTS[model_name]:
            return False
        
        req = cls.MODEL_REQUIREMENTS[model_name][training_type]
        required_gpu_type = req["gpu_type"]
        required_num_gpus = req["num_gpus"]
        
        # Calculate the minimum compute power needed
        min_power_needed = cls.GPU_POWER_RATINGS[required_gpu_type] * required_num_gpus
        
        # Add 10% buffer to account for overhead
        min_power_with_buffer = int(min_power_needed * 1.1)
        
        # Round to nearest 100
        min_power_with_buffer = round(min_power_with_buffer / 100) * 100
        
        return compute_power >= min_power_with_buffer

    @classmethod
    def get_required_compute_power(cls, model_name: str, training_type: str = "lora") -> int:
        """
        Calculate the minimum compute power required for a specific model and training type.
        Returns the value in multiples of 100.
        """
        if model_name not in cls.MODEL_REQUIREMENTS or training_type not in cls.MODEL_REQUIREMENTS[model_name]:
            return 0
        
        req = cls.MODEL_REQUIREMENTS[model_name][training_type]
        required_gpu_type = req["gpu_type"]
        required_num_gpus = req["num_gpus"]
        
        # Calculate the minimum compute power needed
        min_power_needed = cls.GPU_POWER_RATINGS[required_gpu_type] * required_num_gpus
        
        # Add 10% buffer to account for overhead
        min_power_with_buffer = int(min_power_needed * 1.1)
        
        # Round to nearest 100
        min_power_with_buffer = round(min_power_with_buffer / 100) * 100
        
        return min_power_with_buffer

    @classmethod
    def get_best_pool_for_job(cls, model_name: str, training_type: str = "lora") -> int:
        """
        Get the recommended compute power pool for a specific job.
        This value can be used directly for the requiredPool parameter when submitting a job.
        Returns the computePower value in multiples of 100.
        """
        return cls.get_required_compute_power(model_name, training_type)

    @classmethod
    def get_suitable_models(cls, compute_power: int) -> Dict[str, List[str]]:
        """
        Get a list of models and training types that can be run with the given compute power.
        Returns a dictionary of model names mapped to lists of supported training types.
        """
        suitable_models = {}
        
        for model_name, training_types in cls.MODEL_REQUIREMENTS.items():
            supported_types = []
            
            for training_type in training_types.keys():
                if cls.can_run_model(compute_power, model_name, training_type):
                    supported_types.append(training_type)
            
            if supported_types:
                suitable_models[model_name] = supported_types
                
        return suitable_models


# Example usage
if __name__ == "__main__":
    # Sample hardware specs (simulated from HardwareInfo.py output)
    sample_specs = {
        "system": {"os": "Linux", "hostname": "node-1"},
        "cpu": {"cores": 32, "speed_mhz": 3200},
        "memory": {"total_mb": 524288},  # 512 GB
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
        }
    }
    
    # Parse specs and calculate compute power
    parsed = ComputePowerClassifier.parse_hardware_specs(sample_specs)
    compute_power = ComputePowerClassifier.calculate_compute_power(parsed)
    
    print(f"Parsed Specs: {json.dumps(parsed, indent=2)}")
    print(f"Compute Power: {compute_power}")
    
    # Check which models can be run
    suitable_models = ComputePowerClassifier.get_suitable_models(compute_power)
    print(f"Suitable Models: {json.dumps(suitable_models, indent=2)}")
    
    # For a specific job, get the required pool
    model = "llm_llama3_1_70b"
    training = "full"
    required_pool = ComputePowerClassifier.get_best_pool_for_job(model, training)
    print(f"Required Pool for {model} ({training}): {required_pool}")
    print(f"Can run {model} ({training})? {ComputePowerClassifier.can_run_model(compute_power, model, training)}")
