#!/usr/bin/env python3

import os
import sys
import json
import platform
import subprocess
import shutil
import re
from datetime import datetime

class HardwareInfo:
    """
    A class to collect hardware information across different platforms.
    Can be used as a library or standalone script.
    """
    
    def __init__(self):
        """Initialize the hardware info collector"""
        self.hardware_info = {
            "collection_time": datetime.now().isoformat(),
            "system": self.get_system_info(),
            "cpu": self.get_cpu_info(),
            "memory": self.get_memory_info(),
            "gpu": {
                "nvidia": self.get_nvidia_gpu_info(),
                "amd": self.get_amd_gpu_info(),
            },
            "disk": self.get_disk_info(),
            "network": self.get_network_info()
        }
    
    def run_command(self, command):
        """Run a command and return its output"""
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
            return result.stdout.strip()
        except Exception as e:
            return f"Error: {str(e)}"
    
    def command_exists(self, command):
        """Check if a command exists in the system"""
        return shutil.which(command) is not None
    
    def get_system_info(self):
        """Get basic system information"""
        system_info = {}
        system_info["os"] = platform.system()
        
        # OS-specific details
        if system_info["os"] == "Linux":
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            system_info["os_version"] = line.split("=")[1].strip().strip('"')
                            break
            else:
                system_info["os_version"] = platform.version()
        else:
            system_info["os_version"] = platform.version()
        
        system_info["kernel"] = platform.release()
        system_info["hostname"] = platform.node()
        system_info["architecture"] = platform.machine()
        system_info["python_version"] = platform.python_version()
        
        return system_info
    
    def get_cpu_info(self):
        """Get CPU information"""
        cpu_info = {}
        os_type = platform.system()
        
        if os_type == "Linux":
            # Model name
            model_output = self.run_command("grep 'model name' /proc/cpuinfo | head -1")
            if model_output:
                cpu_info["model"] = model_output.split(":")[1].strip()
            else:
                cpu_info["model"] = "Unknown"
            
            # Core count
            cpu_info["cores"] = int(self.run_command("grep -c processor /proc/cpuinfo") or "0")
            
            # CPU Speed
            speed_output = self.run_command("grep 'cpu MHz' /proc/cpuinfo | head -1")
            if speed_output:
                try:
                    cpu_info["speed_mhz"] = int(float(speed_output.split(":")[1].strip()))
                except (ValueError, IndexError):
                    cpu_info["speed_mhz"] = 0
            else:
                cpu_info["speed_mhz"] = 0
        else:
            # Default for other platforms
            cpu_info["model"] = platform.processor() or "Unknown"
            cpu_info["cores"] = os.cpu_count() or 0
            cpu_info["speed_mhz"] = 0
            
        return cpu_info
    
    def get_memory_info(self):
        """Get memory information"""
        memory_info = {}
        os_type = platform.system()
        
        if os_type == "Linux":
            if self.command_exists("free"):
                mem_output = self.run_command("free -m | grep Mem:")
                if mem_output:
                    parts = mem_output.split()
                    if len(parts) >= 2:
                        memory_info["total_mb"] = int(parts[1])
            else:
                mem_output = self.run_command("grep MemTotal /proc/meminfo")
                if mem_output:
                    match = re.search(r'(\d+)', mem_output)
                    if match:
                        # Convert KB to MB
                        memory_info["total_mb"] = int(int(match.group(1)) / 1024)
        
        # If we couldn't determine memory, use psutil as fallback
        if "total_mb" not in memory_info:
            try:
                import psutil
                memory_info["total_mb"] = int(psutil.virtual_memory().total / 1024 / 1024)
            except (ImportError, AttributeError):
                memory_info["total_mb"] = 0
                
        return memory_info
    
    def get_nvidia_gpu_info(self):
        """Get NVIDIA GPU information"""
        if not self.command_exists("nvidia-smi"):
            return {"available": False}
        
        gpu_info = {"available": True}
        
        # Get GPU count
        count_output = self.run_command("nvidia-smi --query-gpu=count --format=csv,noheader")
        try:
            gpu_info["count"] = int(count_output)
        except (ValueError, TypeError):
            gpu_info["count"] = 0
            
        if gpu_info["count"] == 0:
            return gpu_info
        
        # Get details for each GPU
        gpu_info["devices"] = []
        
        for i in range(gpu_info["count"]):
            device = {}
            
            # Get model
            device["model"] = self.run_command(f"nvidia-smi --query-gpu=name --format=csv,noheader -i {i}")
            
            # Get memory
            mem_output = self.run_command(f"nvidia-smi --query-gpu=memory.total --format=csv,noheader -i {i}")
            if mem_output:
                match = re.search(r'(\d+)', mem_output)
                if match:
                    device["memory_mb"] = int(match.group(1))
                else:
                    device["memory_mb"] = 0
            else:
                device["memory_mb"] = 0
            
            # Get compute capability
            device["compute_capability"] = self.run_command(f"nvidia-smi --query-gpu=compute_cap --format=csv,noheader -i {i}") or "Unknown"
            
            # Get utilization
            util_output = self.run_command(f"nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader -i {i}")
            if util_output:
                match = re.search(r'(\d+)', util_output)
                if match:
                    device["utilization_percent"] = int(match.group(1))
                else:
                    device["utilization_percent"] = 0
            else:
                device["utilization_percent"] = 0
                
            gpu_info["devices"].append(device)
            
        return gpu_info
    
    def get_amd_gpu_info(self):
        """Get AMD GPU information"""
        if platform.system() != "Linux" or not self.command_exists("rocm-smi"):
            return {"available": False}
        
        gpu_info = {"available": True}
        
        # Get GPU count
        count_output = self.run_command("rocm-smi --showcount 2>/dev/null | grep 'GPU count'")
        try:
            gpu_info["count"] = int(re.search(r'(\d+)', count_output).group(1))
        except (ValueError, AttributeError):
            gpu_info["count"] = 0
            
        if gpu_info["count"] == 0:
            return gpu_info
        
        # Get details for each GPU
        gpu_info["devices"] = []
        
        for i in range(gpu_info["count"]):
            device = {}
            
            # Get model
            model_output = self.run_command(f"rocm-smi --showproductname -d {i} 2>/dev/null | grep 'Card'")
            if model_output:
                device["model"] = model_output.split(':')[1].strip()
            else:
                device["model"] = "Unknown"
            
            # Get memory
            mem_output = self.run_command(f"rocm-smi --showmeminfo vram -d {i} 2>/dev/null | grep 'total'")
            if mem_output:
                match = re.search(r'(\d+)', mem_output)
                if match:
                    mem_value = int(match.group(1))
                    # Convert to MB if needed
                    if mem_value > 1000000:
                        mem_value = int(mem_value / 1024 / 1024)
                    device["memory_mb"] = mem_value
                else:
                    device["memory_mb"] = 0
            else:
                device["memory_mb"] = 0
            
            # Get utilization
            util_output = self.run_command(f"rocm-smi --showuse -d {i} 2>/dev/null | grep 'GPU use'")
            if util_output:
                match = re.search(r'(\d+)%', util_output)
                if match:
                    device["utilization_percent"] = int(match.group(1))
                else:
                    device["utilization_percent"] = 0
            else:
                device["utilization_percent"] = 0
                
            gpu_info["devices"].append(device)
            
        return gpu_info
    
        if not self.command_exists("system_profiler"):
            return {"available": False}
        
        gpu_info = {}
        
        # Get GPU info using system_profiler
        gpu_output = self.run_command("system_profiler SPDisplaysDataType 2>/dev/null")
        
        if not gpu_output or "Chipset Model:" not in gpu_output:
            return {"available": False}
        
        gpu_info["available"] = True
        
        # Count GPUs by counting "Chipset Model:" occurrences
        gpu_info["count"] = gpu_output.count("Chipset Model:")
        
        if gpu_info["count"] == 0:
            return gpu_info
        
        # Parse GPU details
        gpu_info["devices"] = []
        
        # Split by sections
        sections = gpu_output.split("Chipset Model:")
        
        for i in range(1, len(sections)):  # Skip first split which is before any "Chipset Model:"
            section = sections[i]
            device = {}
            
            # Get model
            device["model"] = section.strip().split("\n")[0].strip()
            
            # Try to get VRAM
            if "VRAM" in section:
                vram_match = re.search(r'VRAM.*?(\d+)\s+MB', section)
                if vram_match:
                    device["memory_mb"] = int(vram_match.group(1))
                else:
                    device["memory_mb"] = 0
            else:
                device["memory_mb"] = 0
            
            # Try to get Metal support
            if "Metal:" in section:
                metal_match = re.search(r'Metal:\s+(.*?)$', section, re.MULTILINE)
                if metal_match:
                    device["metal_support"] = metal_match.group(1).strip()
                else:
                    device["metal_support"] = "Unknown"
            else:
                device["metal_support"] = "Unknown"
                
            gpu_info["devices"].append(device)
            
        return gpu_info
    
    def get_disk_info(self):
        """Get disk information"""
        disk_info = {}
        
        if self.command_exists("df"):
            # Get root partition info
            df_output = self.run_command("df -h /")
            if df_output:
                lines = df_output.strip().split('\n')
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        disk_info["total"] = parts[1]
                        disk_info["available"] = parts[3]
                        disk_info["used_percent"] = parts[4]
        
        # If we couldn't determine disk info, use psutil as fallback
        if not disk_info:
            try:
                import psutil
                disk_usage = psutil.disk_usage('/')
                disk_info["total"] = f"{disk_usage.total / (1024**3):.1f}G"
                disk_info["available"] = f"{disk_usage.free / (1024**3):.1f}G"
                disk_info["used_percent"] = f"{disk_usage.percent}%"
            except (ImportError, AttributeError):
                disk_info["total"] = "Unknown"
                disk_info["available"] = "Unknown"
                disk_info["used_percent"] = "Unknown"
                
        return disk_info
    
    def get_network_info(self):
        """Get network information"""
        network_info = {}
        os_type = platform.system()
        
        # Try to get primary non-loopback IP
        if os_type == "Linux":
            if self.command_exists("ip"):
                ip_output = self.run_command("ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}'")
                if ip_output:
                    network_info["primary_ip"] = ip_output.split("\n")[0]
            elif self.command_exists("ifconfig"):
                ifconfig_output = self.run_command("ifconfig")
                ip_match = re.search(r'inet (?:addr:)?(\d+\.\d+\.\d+\.\d+).*?(?:netmask|Mask)', ifconfig_output, re.DOTALL)
                if ip_match and "127.0.0.1" not in ip_match.group(1):
                    network_info["primary_ip"] = ip_match.group(1)
        
        # If we couldn't determine IP, use socket as fallback
        if "primary_ip" not in network_info:
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                network_info["primary_ip"] = s.getsockname()[0]
                s.close()
            except:
                network_info["primary_ip"] = "Unknown"
                
        return network_info
    
    def get_all_info(self):
        """Get all hardware information"""
        return self.hardware_info
    
    def save_to_file(self, output_file="node_specs.json"):
        """Save hardware info to a JSON file"""
        with open(output_file, 'w') as f:
            json.dump(self.hardware_info, f, indent=2)
        return output_file
    
    def print_summary(self):
        """Print a summary of hardware info to stdout"""
        print("\nHardware Summary:")
        print(f"OS: {self.hardware_info['system']['os']} {self.hardware_info['system']['os_version']}")
        print(f"CPU: {self.hardware_info['cpu']['model']} ({self.hardware_info['cpu']['cores']} cores)")
        print(f"Memory: {self.hardware_info['memory']['total_mb']} MB")
        
        # GPU summary
        if self.hardware_info['gpu']['nvidia']['available']:
            print(f"NVIDIA GPUs: {self.hardware_info['gpu']['nvidia']['count']}")
        if self.hardware_info['gpu']['amd']['available']:
            print(f"AMD GPUs: {self.hardware_info['gpu']['amd']['count']}")
        
        print(f"Disk: {self.hardware_info['disk']['used_percent']} used of {self.hardware_info['disk']['total']}")
        print(f"IP: {self.hardware_info['network']['primary_ip']}")


# Can be used as a standalone script
if __name__ == "__main__":
    hw_info = HardwareInfo()
    output_file = hw_info.save_to_file()
    print(f"Hardware specifications have been saved to {output_file}")
    hw_info.print_summary()