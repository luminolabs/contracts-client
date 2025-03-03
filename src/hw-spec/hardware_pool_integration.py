#!/usr/bin/env python3

import json
import os
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

# Import our hardware detection and classification modules
from hardware_info import HardwareInfo
from compute_power_classifier import ComputePowerClassifier

class HardwarePoolIntegration:
    """
    Integrates hardware detection with Lumino node pool assignment.
    Calculates appropriate compute power ratings and maintains a persistent
    hardware profile for the node.
    """
    
    def __init__(self, data_dir: str, logger: Optional[logging.Logger] = None):
        """
        Initialize the hardware pool integration.
        
        Args:
            data_dir: Directory to store hardware profile data
            logger: Optional logger instance to use
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.hw_profile_path = self.data_dir / "hardware_profile.json"
        
        # Set up logging
        self.logger = logger or logging.getLogger("HardwarePoolIntegration")
        
        # Load existing profile or create new one
        self.hw_profile = self._load_hw_profile()
    
    def _load_hw_profile(self) -> Dict:
        """Load hardware profile from disk or initialize a new one."""
        if self.hw_profile_path.exists():
            try:
                with open(self.hw_profile_path, 'r') as f:
                    profile = json.load(f)
                    self.logger.info(f"Loaded existing hardware profile with compute power: {profile.get('compute_power', 'unknown')}")
                    return profile
            except Exception as e:
                self.logger.warning(f"Error loading hardware profile: {e}. Creating new profile.")
        
        # Create default profile
        return {
            "compute_power": 0,
            "hardware_specs": {},
            "compatible_models": {},
            "last_updated": None
        }
    
    def _save_hw_profile(self) -> None:
        """Save hardware profile to disk."""
        with open(self.hw_profile_path, 'w') as f:
            json.dump(self.hw_profile, f, indent=2)
        self.logger.info(f"Saved hardware profile to {self.hw_profile_path}")
    
    def detect_hardware(self) -> Dict:
        """
        Detect hardware specifications using HardwareInfo.
        Returns the detected hardware specifications.
        """
        self.logger.info("Detecting hardware specifications...")
        hw_info = HardwareInfo()
        specs = hw_info.get_all_info()
        
        # Save the raw specs to the profile
        self.hw_profile["hardware_specs"] = specs
        self.hw_profile["last_updated"] = specs["collection_time"]
        self._save_hw_profile()
        
        return specs
    
    def calculate_compute_power(self, force_recalculate: bool = False) -> int:
        """
        Calculate the compute power for the node based on hardware specs.
        
        Args:
            force_recalculate: If True, re-detect hardware before calculating
            
        Returns:
            The calculated compute power value
        """
        # Check if we need to detect hardware
        if force_recalculate or not self.hw_profile.get("hardware_specs"):
            self.detect_hardware()
        
        # Parse the hardware specs
        specs = self.hw_profile["hardware_specs"]
        parsed_specs = ComputePowerClassifier.parse_hardware_specs(specs)
        
        # Calculate compute power
        compute_power = ComputePowerClassifier.calculate_compute_power(parsed_specs)
        
        # Update the profile
        self.hw_profile["compute_power"] = compute_power
        
        # Calculate compatible models
        compatible_models = ComputePowerClassifier.get_suitable_models(compute_power)
        self.hw_profile["compatible_models"] = compatible_models
        
        self._save_hw_profile()
        self.logger.info(f"Calculated compute power: {compute_power}")
        
        return compute_power
    
    def get_compute_power(self) -> int:
        """
        Get the current compute power rating for this node.
        If not available, triggers a calculation.
        
        Returns:
            The compute power value
        """
        if "compute_power" not in self.hw_profile or self.hw_profile["compute_power"] == 0:
            return self.calculate_compute_power()
        return self.hw_profile["compute_power"]
    
    def get_compatible_models(self) -> Dict:
        """
        Get models compatible with this node's compute power.
        
        Returns:
            Dict mapping model names to lists of supported training types
        """
        # Ensure we have compatible models calculated
        if not self.hw_profile.get("compatible_models"):
            self.calculate_compute_power()
        
        return self.hw_profile.get("compatible_models", {})
    
    def can_run_job(self, model_name: str, training_type: str = "lora") -> bool:
        """
        Check if this node can run a specific job.
        
        Args:
            model_name: The model to check
            training_type: The training type (lora, qlora, full)
            
        Returns:
            True if the job can run on this node
        """
        compute_power = self.get_compute_power()
        return ComputePowerClassifier.can_run_model(compute_power, model_name, training_type)
    
    def get_recommended_compute_rating(self) -> int:
        """
        Get the recommended compute rating to use when registering this node.
        This value should be used with nodeManager.registerNode().
        
        Returns:
            The compute rating to use for node registration
        """
        # Get current compute power
        compute_power = self.get_compute_power()
        
        # Convert to compute rating scale used by contracts
        # The compute_power is already in multiples of 100
        # We divide by 100 to get the compute rating expected by the contract
        compute_rating = compute_power // 100
        
        # Ensure minimum rating of 1
        compute_rating = max(1, compute_rating)
        
        self.logger.info(f"Recommended compute rating for registration: {compute_rating}")
        return compute_rating
    
    def print_hardware_summary(self) -> None:
        """Print a summary of the node's hardware capabilities."""
        compute_power = self.get_compute_power()
        compatible_models = self.get_compatible_models()
        
        print("\n=== Node Hardware Profile ===")
        print(f"Compute Power: {compute_power}")
        print(f"Registration Rating: {self.get_recommended_compute_rating()}")
        
        if compatible_models:
            print("\nCompatible Models:")
            for model, training_types in compatible_models.items():
                print(f"  {model}: {', '.join(training_types)}")
        else:
            print("\nNo compatible models found for this hardware.")
        
        # Print some basic hardware info if available
        specs = self.hw_profile.get("hardware_specs", {})
        if specs:
            print("\nHardware Summary:")
            
            # System info
            if "system" in specs:
                system = specs["system"]
                print(f"OS: {system.get('os', 'Unknown')} {system.get('os_version', '')}")
            
            # CPU info
            if "cpu" in specs:
                cpu = specs["cpu"]
                print(f"CPU: {cpu.get('model', 'Unknown')} ({cpu.get('cores', 0)} cores)")
            
            # Memory info
            if "memory" in specs:
                memory_mb = specs["memory"].get("total_mb", 0)
                memory_gb = memory_mb / 1024
                print(f"Memory: {memory_gb:.1f} GB")
            
            # GPU info
            if "gpu" in specs and "nvidia" in specs["gpu"]:
                nvidia = specs["gpu"]["nvidia"]
                if nvidia.get("available", False):
                    print(f"NVIDIA GPUs: {nvidia.get('count', 0)}")
                    
                    # Print each GPU
                    for i, device in enumerate(nvidia.get("devices", [])):
                        model = device.get("model", "Unknown")
                        memory_mb = device.get("memory_mb", 0)
                        memory_gb = memory_mb / 1024
                        print(f"  GPU {i+1}: {model} ({memory_gb:.1f} GB)")
        
        print("==============================")

# Example for job submission with compute power matching
def example_job_submission():
    """
    Example demonstrating how to use compute power classification for job submission.
    
    This shows:
    1. How to detect a node's compute power 
    2. How to determine job requirements
    3. How to match jobs to appropriate nodes
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("JobSubmissionExample")
    
    # 1. Node side - Detect hardware and calculate compute power
    integration = HardwarePoolIntegration("./cache", logger)
    compute_power = integration.calculate_compute_power(force_recalculate=True)
    registration_rating = integration.get_recommended_compute_rating()
    
    logger.info(f"Node compute power: {compute_power}")
    logger.info(f"Registration rating: {registration_rating}")
    
    # 2. User side - Determine job requirements 
    models_to_try = [
        ("llm_llama3_1_8b", "lora"),
        ("llm_llama3_1_8b", "full"),
        ("llm_llama3_1_70b", "qlora"),
        ("llm_llama3_1_70b", "full")
    ]
    
    logger.info("\nJOB SUBMISSION EXAMPLES:")
    for model, training_type in models_to_try:
        # Calculate required pool for this job
        required_pool = ComputePowerClassifier.get_best_pool_for_job(model, training_type)
        
        # Check if this node could run this job
        can_run = integration.can_run_job(model, training_type)
        
        logger.info(f"Job: {model} ({training_type})")
        logger.info(f"  Required pool: {required_pool}")
        logger.info(f"  Can this node run it? {can_run}")
        logger.info(f"  Submit with: client.submit_job(args, '{model}', {required_pool})")
        logger.info("")

if __name__ == "__main__":
    # Run the standard hardware analysis
    integration = HardwarePoolIntegration("./cache")
    integration.print_hardware_summary()
    
    # Run the job submission example
    example_job_submission()