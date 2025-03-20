import unittest
import pynvml
from unittest.mock import patch, MagicMock

from lumino.contracts_client.compute_power import get_compute_power


class TestComputePower(unittest.TestCase):
    """Tests for compute_power.py functions"""

    def setUp(self):
        # Common setup for GPU mock objects
        self.mock_handle = MagicMock()
        self.mock_mem_info = MagicMock()
        
        # Default RAM value (200GB)
        self.ram_gb = 200 * 1024**3

    def test_no_gpu_detected(self):
        """Test when no GPUs are detected"""
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=0), \
             patch('pynvml.nvmlShutdown'):
            result = get_compute_power()
            self.assertEqual(result, 0)

    def test_nvml_error(self):
        """Test when NVML raises an error"""
        with patch('pynvml.nvmlInit', side_effect=pynvml.NVMLError("NVML Error")):
            result = get_compute_power()
            self.assertEqual(result, 0)

    def test_v100_single_gpu(self):
        """Test for a single V100 GPU with sufficient RAM"""
        self.mock_mem_info.total = 32 * 1024**3  # 32GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=1), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="Tesla V100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('psutil.virtual_memory') as mock_virt_mem, \
             patch('pynvml.nvmlShutdown'):
            
            # Set system RAM to sufficient value
            mock_vm = MagicMock()
            mock_vm.total = 41 * 1024**3  # 41GB RAM (min is 40GB)
            mock_virt_mem.return_value = mock_vm
            
            result = get_compute_power()
            self.assertEqual(result, 100)  # Base power 100 for 1 V100

    def test_v100_single_gpu_insufficient_ram(self):
        """Test for a single V100 GPU with insufficient RAM"""
        self.mock_mem_info.total = 32 * 1024**3  # 32GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=1), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="Tesla V100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('psutil.virtual_memory') as mock_virt_mem, \
             patch('pynvml.nvmlShutdown'):
            
            # Set system RAM to insufficient value
            # The function divides by (1024**3) to convert to GB, so we need to use a value
            # that will be less than the min required (40GB for V100) after this conversion
            mock_vm = MagicMock()
            mock_vm.total = 39 * 1024**3  # 39GB RAM (minimum is 40GB in the function)
            mock_virt_mem.return_value = mock_vm
            
            result = get_compute_power()
            self.assertEqual(result, 0)  # Should return 0 due to insufficient RAM

    def test_v100_unsupported_gpu_count(self):
        """Test V100 with unsupported number of GPUs (not 1, 4, or 8)"""
        self.mock_mem_info.total = 32 * 1024**3  # 32GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=2), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="Tesla V100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('pynvml.nvmlShutdown'):
            
            result = get_compute_power()
            self.assertEqual(result, 0)  # Should return 0 for unsupported GPU count

    def test_v100_multiple_supported_gpus(self):
        """Test multiple V100 GPUs with supported count (4)"""
        self.mock_mem_info.total = 32 * 1024**3  # 32GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=4), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="Tesla V100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('psutil.virtual_memory') as mock_virt_mem, \
             patch('pynvml.nvmlShutdown'):
            
            # Set system RAM to sufficient value
            mock_vm = MagicMock()
            mock_vm.total = 161 * 1024**3  # 161GB RAM (min is 40GB * 4 = 160GB)
            mock_virt_mem.return_value = mock_vm
            
            result = get_compute_power()
            self.assertEqual(result, 400)  # Base power 100 * 4 V100s = 400

    def test_a100_40gb(self):
        """Test for a single A100 40GB GPU"""
        self.mock_mem_info.total = 40 * 1024**3  # 40GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=1), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="NVIDIA A100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('psutil.virtual_memory') as mock_virt_mem, \
             patch('pynvml.nvmlShutdown'):
            
            # Set system RAM to sufficient value
            mock_vm = MagicMock()
            mock_vm.total = 81 * 1024**3  # 81GB RAM (min is 80GB)
            mock_virt_mem.return_value = mock_vm
            
            result = get_compute_power()
            self.assertEqual(result, 150)  # Base power 150 for 1 A100 40GB

    def test_a100_80gb(self):
        """Test for a single A100 80GB GPU"""
        self.mock_mem_info.total = 80 * 1024**3  # 80GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=1), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="NVIDIA A100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('psutil.virtual_memory') as mock_virt_mem, \
             patch('pynvml.nvmlShutdown'):
            
            # Set system RAM to sufficient value
            mock_vm = MagicMock()
            mock_vm.total = 166 * 1024**3  # 166GB RAM (min is 165GB)
            mock_virt_mem.return_value = mock_vm
            
            result = get_compute_power()
            self.assertEqual(result, 160)  # Base power 160 for 1 A100 80GB

    def test_a100_unsupported_gpu_count(self):
        """Test A100 with unsupported number of GPUs (not 1, 2, 4, or 8)"""
        self.mock_mem_info.total = 80 * 1024**3  # 80GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=3), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="NVIDIA A100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('pynvml.nvmlShutdown'):
            
            result = get_compute_power()
            self.assertEqual(result, 0)  # Should return 0 for unsupported GPU count

    def test_h100_single_gpu(self):
        """Test for a single H100 GPU with sufficient RAM"""
        self.mock_mem_info.total = 80 * 1024**3  # 80GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=1), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="NVIDIA H100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('psutil.virtual_memory') as mock_virt_mem, \
             patch('pynvml.nvmlShutdown'):
            
            # Set system RAM to sufficient value
            mock_vm = MagicMock()
            mock_vm.total = 231 * 1024**3  # 231GB RAM (min is 230GB)
            mock_virt_mem.return_value = mock_vm
            
            result = get_compute_power()
            self.assertEqual(result, 250)  # Base power 250 for 1 H100

    def test_h100_single_gpu_insufficient_ram(self):
        """Test for a single H100 GPU with insufficient RAM"""
        self.mock_mem_info.total = 80 * 1024**3  # 80GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=1), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="NVIDIA H100"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('psutil.virtual_memory') as mock_virt_mem, \
             patch('pynvml.nvmlShutdown'):
            
            # Set system RAM to insufficient value
            mock_vm = MagicMock()
            mock_vm.total = 229 * 1024**3  # 229GB RAM (min is 230GB in the function)
            mock_virt_mem.return_value = mock_vm
            
            result = get_compute_power()
            self.assertEqual(result, 0)  # Should return 0 due to insufficient RAM

    def test_unsupported_gpu(self):
        """Test for an unsupported GPU type"""
        self.mock_mem_info.total = 16 * 1024**3  # 16GB VRAM
        
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetCount', return_value=1), \
             patch('pynvml.nvmlDeviceGetHandleByIndex', return_value=self.mock_handle), \
             patch('pynvml.nvmlDeviceGetName', return_value="NVIDIA RTX 4090"), \
             patch('pynvml.nvmlDeviceGetMemoryInfo', return_value=self.mock_mem_info), \
             patch('pynvml.nvmlShutdown'):
            
            result = get_compute_power()
            self.assertEqual(result, 0)  # Should return 0 for unsupported GPU type


if __name__ == '__main__':
    unittest.main()