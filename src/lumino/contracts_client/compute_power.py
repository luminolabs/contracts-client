import psutil
import pynvml


def get_compute_power():
    """
    Detects NVIDIA GPUs and returns a compute power number based on the GPU configuration.
    Returns 0 if no NVIDIA GPUs are detected, if GPUs are not supported, or if system RAM is insufficient.
    Supported GPUs: V100 (1, 4, or 8 GPUs), A100 40GB, A100 80GB, H100 80GB (1, 2, 4, or 8 GPUs).
    """
    initialized = False
    try:
        # Initialize the NVML library
        pynvml.nvmlInit()
        initialized = True

        # Get the number of GPUs
        num_gpus = pynvml.nvmlDeviceGetCount()
        if num_gpus == 0:
            return 0

        # Get information from the first GPU (assuming all GPUs on the node are identical)
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle).upper()
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_memory = mem_info.total

        # Determine GPU type and assign base compute power
        if "V100" in name:
            base_power = 100
            # V100 only supports 1, 4, or 8 GPUs
            if num_gpus not in [1, 4, 8]:
                return 0
        elif "A100" in name:
            if total_memory > 50e9:  # Threshold to distinguish 40GB vs 80GB
                base_power = 160  # A100 80GB
            else:
                base_power = 150  # A100 40GB
            # A100 supports 1, 2, 4, or 8 GPUs
            if num_gpus not in [1, 2, 4, 8]:
                return 0
        elif "H100" in name:
            base_power = 250  # H100 80GB
            # H100 supports 1, 2, 4, or 8 GPUs
            if num_gpus not in [1, 2, 4, 8]:
                return 0
        else:
            base_power = 0  # Unsupported GPU

        # Calculate total compute power
        compute_power = base_power * num_gpus

        # Check if system RAM is sufficient
        if compute_power > 0:
            current_RAM = psutil.virtual_memory().total / (1024 ** 3)  # Current RAM in GB

            min_RAM_per_GPU = {
                100: 40,   # V100
                150: 80,   # A100 40GB
                160: 165,  # A100 80GB
                250: 230   # H100 80GB
            }.get(base_power, 0)
            min_RAM = min_RAM_per_GPU * num_gpus

            if current_RAM < min_RAM:
                return 0  # Insufficient RAM

        return compute_power

    except pynvml.NVMLError:
        # Return 0 if any NVML error occurs (e.g., no NVIDIA driver)
        return 0

    finally:
        # Clean up only if initialization was successful
        if initialized:
            pynvml.nvmlShutdown()


if __name__ == "__main__":
    # Test the get_compute_power function when the script is run directly
    power = get_compute_power()
    print(f"Detected Compute Power: {power}")
