#!/bin/bash

# Script to collect node hardware specifications
# Outputs CPU, Memory, and GPU details in JSON format
# Works on Linux and macOS

OUTPUT_FILE="node_specs.json"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect OS
OS_TYPE=$(uname -s)

# Initialize JSON structure
echo "{" > $OUTPUT_FILE

# Add OS information first
echo "  \"system\": {" >> $OUTPUT_FILE

# OS Information 
if [ "$OS_TYPE" = "Linux" ]; then
    if [ -f /etc/os-release ]; then
        OS_INFO=$(cat /etc/os-release | grep PRETTY_NAME | cut -d "=" -f2 | tr -d '"')
    else
        OS_INFO="Linux $(uname -r)"
    fi
elif [ "$OS_TYPE" = "Darwin" ]; then
    OS_INFO="macOS $(sw_vers -productVersion)"
else
    OS_INFO="$OS_TYPE"
fi
echo "    \"os\": \"$OS_INFO\"," >> $OUTPUT_FILE

# Kernel version
KERNEL_VERSION=$(uname -r)
echo "    \"kernel\": \"$KERNEL_VERSION\"," >> $OUTPUT_FILE

# Hostname
HOSTNAME=$(hostname)
echo "    \"hostname\": \"$HOSTNAME\"" >> $OUTPUT_FILE

echo "  }," >> $OUTPUT_FILE

# Get CPU information
echo "  \"cpu\": {" >> $OUTPUT_FILE

# CPU Model and details by OS type
if [ "$OS_TYPE" = "Linux" ]; then
    # CPU Model
    CPU_MODEL=$(grep "model name" /proc/cpuinfo | head -n1 | cut -d ":" -f2 | sed 's/^[ \t]*//')
    echo "    \"model\": \"$CPU_MODEL\"," >> $OUTPUT_FILE
    
    # CPU Cores
    CPU_CORES=$(grep -c "processor" /proc/cpuinfo)
    echo "    \"cores\": $CPU_CORES," >> $OUTPUT_FILE
    
    # CPU Speed (MHz)
    CPU_SPEED=$(grep "cpu MHz" /proc/cpuinfo | head -n1 | cut -d ":" -f2 | sed 's/^[ \t]*//' | cut -d "." -f1)
    echo "    \"speed_mhz\": $CPU_SPEED" >> $OUTPUT_FILE
elif [ "$OS_TYPE" = "Darwin" ]; then
    # macOS CPU info
    if command_exists sysctl; then
        # CPU Model
        CPU_MODEL=$(sysctl -n machdep.cpu.brand_string)
        echo "    \"model\": \"$CPU_MODEL\"," >> $OUTPUT_FILE
        
        # CPU Cores (physical)
        CPU_CORES=$(sysctl -n hw.physicalcpu)
        LOGICAL_CORES=$(sysctl -n hw.logicalcpu)
        echo "    \"cores\": $CPU_CORES," >> $OUTPUT_FILE
        echo "    \"logical_cores\": $LOGICAL_CORES," >> $OUTPUT_FILE
        
        # CPU Speed (MHz)
        CPU_SPEED=$(sysctl -n hw.cpufrequency 2>/dev/null || echo 0)
        CPU_SPEED=$((CPU_SPEED / 1000000)) # Convert to MHz
        echo "    \"speed_mhz\": $CPU_SPEED" >> $OUTPUT_FILE
    else
        echo "    \"model\": \"Unknown (sysctl not available)\"," >> $OUTPUT_FILE
        echo "    \"cores\": 0," >> $OUTPUT_FILE
        echo "    \"speed_mhz\": 0" >> $OUTPUT_FILE
    fi
else
    echo "    \"model\": \"Unknown OS\"," >> $OUTPUT_FILE
    echo "    \"cores\": 0," >> $OUTPUT_FILE
    echo "    \"speed_mhz\": 0" >> $OUTPUT_FILE
fi

echo "  }," >> $OUTPUT_FILE

# Get Memory information
echo "  \"memory\": {" >> $OUTPUT_FILE

# Memory by OS type
if [ "$OS_TYPE" = "Linux" ]; then
    if command_exists free; then
        TOTAL_MEM=$(free -m | grep "Mem:" | awk '{print $2}')
        echo "    \"total_mb\": $TOTAL_MEM" >> $OUTPUT_FILE
    else
        MEM_INFO=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        # Convert from KB to MB
        TOTAL_MEM=$((MEM_INFO / 1024))
        echo "    \"total_mb\": $TOTAL_MEM" >> $OUTPUT_FILE
    fi
elif [ "$OS_TYPE" = "Darwin" ]; then
    if command_exists sysctl; then
        # macOS memory in bytes, convert to MB
        TOTAL_MEM=$(sysctl -n hw.memsize)
        TOTAL_MEM=$((TOTAL_MEM / 1024 / 1024))
        echo "    \"total_mb\": $TOTAL_MEM" >> $OUTPUT_FILE
    else
        echo "    \"total_mb\": 0" >> $OUTPUT_FILE
    fi
else
    echo "    \"total_mb\": 0" >> $OUTPUT_FILE
fi

echo "  }," >> $OUTPUT_FILE

# Get GPU information
echo "  \"gpu\": {" >> $OUTPUT_FILE

# NVIDIA GPUs (Linux and macOS)
if command_exists nvidia-smi; then
    echo "    \"nvidia\": {" >> $OUTPUT_FILE
    echo "      \"available\": true," >> $OUTPUT_FILE
    
    # Get GPU count
    GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader 2>/dev/null || echo 0)
    echo "      \"count\": $GPU_COUNT," >> $OUTPUT_FILE
    
    # Get GPU details as an array
    echo "      \"devices\": [" >> $OUTPUT_FILE
    
    # Loop through each GPU
    for ((i=0; i<$GPU_COUNT; i++)); do
        if [ $i -gt 0 ]; then
            echo "        }," >> $OUTPUT_FILE
        fi
        
        # Get GPU model
        GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader -i $i 2>/dev/null || echo "Unknown")
        echo "        {" >> $OUTPUT_FILE
        echo "          \"model\": \"$GPU_MODEL\"," >> $OUTPUT_FILE
        
        # Get GPU memory
        GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader -i $i 2>/dev/null | cut -d " " -f1 || echo 0)
        echo "          \"memory_mb\": $GPU_MEM," >> $OUTPUT_FILE
        
        # Get GPU compute capability if possible
        COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader -i $i 2>/dev/null || echo "Unknown")
        echo "          \"compute_capability\": \"$COMPUTE_CAP\"," >> $OUTPUT_FILE
        
        # Get GPU utilization
        GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader -i $i 2>/dev/null | cut -d " " -f1 || echo 0)
        echo "          \"utilization_percent\": $GPU_UTIL" >> $OUTPUT_FILE
    done
    
    # Close the last GPU object and the devices array
    if [ $GPU_COUNT -gt 0 ]; then
        echo "        }" >> $OUTPUT_FILE
    fi
    echo "      ]" >> $OUTPUT_FILE
    echo "    }," >> $OUTPUT_FILE
else
    echo "    \"nvidia\": {" >> $OUTPUT_FILE
    echo "      \"available\": false" >> $OUTPUT_FILE
    echo "    }," >> $OUTPUT_FILE
fi

# AMD GPUs (Linux)
if [ "$OS_TYPE" = "Linux" ] && command_exists rocm-smi; then
    echo "    \"amd\": {" >> $OUTPUT_FILE
    echo "      \"available\": true," >> $OUTPUT_FILE
    
    # Get AMD GPU count
    AMD_GPU_COUNT=$(rocm-smi --showcount 2>/dev/null | grep "GPU count" | awk '{print $3}' || echo 0)
    echo "      \"count\": $AMD_GPU_COUNT," >> $OUTPUT_FILE
    
    # Get GPU details as an array
    echo "      \"devices\": [" >> $OUTPUT_FILE
    
    # Loop through each GPU
    for ((i=0; i<$AMD_GPU_COUNT; i++)); do
        if [ $i -gt 0 ]; then
            echo "        }," >> $OUTPUT_FILE
        fi
        
        echo "        {" >> $OUTPUT_FILE
        
        # Get GPU model
        AMD_GPU_MODEL=$(rocm-smi --showproductname -d $i 2>/dev/null | grep "Card" | sed 's/.*://' | sed 's/^ *//' || echo "Unknown")
        echo "          \"model\": \"$AMD_GPU_MODEL\"," >> $OUTPUT_FILE
        
        # Get GPU memory
        AMD_GPU_MEM=$(rocm-smi --showmeminfo vram -d $i 2>/dev/null | grep "total" | awk '{print $2}' || echo 0)
        # Convert from bytes to MB if needed
        if [ $AMD_GPU_MEM -gt 1000000 ]; then
            AMD_GPU_MEM=$((AMD_GPU_MEM / 1024 / 1024))
        fi
        echo "          \"memory_mb\": $AMD_GPU_MEM," >> $OUTPUT_FILE
        
        # Get GPU utilization
        AMD_GPU_UTIL=$(rocm-smi --showuse -d $i 2>/dev/null | grep "GPU use" | awk '{print $3}' | tr -d '%' || echo 0)
        echo "          \"utilization_percent\": $AMD_GPU_UTIL" >> $OUTPUT_FILE
    done
    
    # Close the last GPU object and the devices array
    if [ $AMD_GPU_COUNT -gt 0 ]; then
        echo "        }" >> $OUTPUT_FILE
    fi
    echo "      ]" >> $OUTPUT_FILE
    echo "    }," >> $OUTPUT_FILE
else
    echo "    \"amd\": {" >> $OUTPUT_FILE
    echo "      \"available\": false" >> $OUTPUT_FILE
    echo "    }," >> $OUTPUT_FILE
fi

# macOS GPU (Apple Silicon or Intel)
if [ "$OS_TYPE" = "Darwin" ]; then
    echo "    \"apple\": {" >> $OUTPUT_FILE
    
    if command_exists system_profiler; then
        # Check if we can get GPU info
        GPU_INFO=$(system_profiler SPDisplaysDataType 2>/dev/null)
        if [ ! -z "$GPU_INFO" ]; then
            echo "      \"available\": true," >> $OUTPUT_FILE
            
            # Count how many graphics cards
            APPLE_GPU_COUNT=$(echo "$GPU_INFO" | grep -c "Chipset Model:")
            echo "      \"count\": $APPLE_GPU_COUNT," >> $OUTPUT_FILE
            
            echo "      \"devices\": [" >> $OUTPUT_FILE
            
            # Parse each GPU - this is trickier in macOS
            FIRST_GPU=true
            while IFS= read -r line; do
                if [[ $line == *"Chipset Model:"* ]]; then
                    if [ "$FIRST_GPU" = "true" ]; then
                        FIRST_GPU=false
                    else
                        echo "        }," >> $OUTPUT_FILE
                    fi
                    
                    echo "        {" >> $OUTPUT_FILE
                    GPU_MODEL=$(echo "$line" | sed 's/.*: //')
                    echo "          \"model\": \"$GPU_MODEL\"," >> $OUTPUT_FILE
                    
                    # Try to get VRAM
                    VRAM_LINE=$(echo "$GPU_INFO" | grep -A 10 "$GPU_MODEL" | grep "VRAM" | head -1)
                    if [ ! -z "$VRAM_LINE" ]; then
                        VRAM_MB=$(echo "$VRAM_LINE" | grep -o '[0-9]\+ MB' | grep -o '[0-9]\+' || echo 0)
                        echo "          \"memory_mb\": $VRAM_MB," >> $OUTPUT_FILE
                    else
                        echo "          \"memory_mb\": 0," >> $OUTPUT_FILE
                    fi
                    
                    # Try to get Metal support
                    METAL_LINE=$(echo "$GPU_INFO" | grep -A 15 "$GPU_MODEL" | grep "Metal:" | head -1)
                    if [ ! -z "$METAL_LINE" ]; then
                        METAL_SUPPORT=$(echo "$METAL_LINE" | sed 's/.*: //')
                        echo "          \"metal_support\": \"$METAL_SUPPORT\"" >> $OUTPUT_FILE
                    else
                        echo "          \"metal_support\": \"Unknown\"" >> $OUTPUT_FILE
                    fi
                fi
            done <<< "$(echo "$GPU_INFO" | grep "Chipset Model:")"
            
            # Close last device
            if [ $APPLE_GPU_COUNT -gt 0 ]; then
                echo "        }" >> $OUTPUT_FILE
            fi
            echo "      ]" >> $OUTPUT_FILE
        else
            echo "      \"available\": false" >> $OUTPUT_FILE
        fi
    else
        echo "      \"available\": false" >> $OUTPUT_FILE
    fi
    
    echo "    }" >> $OUTPUT_FILE
else
    echo "    \"apple\": {" >> $OUTPUT_FILE
    echo "      \"available\": false" >> $OUTPUT_FILE
    echo "    }" >> $OUTPUT_FILE
fi

echo "  }," >> $OUTPUT_FILE

# Get disk information 
echo "  \"disk\": {" >> $OUTPUT_FILE

if [ "$OS_TYPE" = "Linux" ]; then
    if command_exists df; then
        TOTAL_DISK=$(df -h / | awk 'NR==2 {print $2}')
        AVAIL_DISK=$(df -h / | awk 'NR==2 {print $4}')
        DISK_USED_PCT=$(df -h / | awk 'NR==2 {print $5}')
        
        echo "    \"total\": \"$TOTAL_DISK\"," >> $OUTPUT_FILE
        echo "    \"available\": \"$AVAIL_DISK\"," >> $OUTPUT_FILE
        echo "    \"used_percent\": \"$DISK_USED_PCT\"" >> $OUTPUT_FILE
    else
        echo "    \"total\": \"Unknown\"," >> $OUTPUT_FILE
        echo "    \"available\": \"Unknown\"," >> $OUTPUT_FILE
        echo "    \"used_percent\": \"Unknown\"" >> $OUTPUT_FILE
    fi
elif [ "$OS_TYPE" = "Darwin" ]; then
    if command_exists df; then
        TOTAL_DISK=$(df -h / | awk 'NR==2 {print $2}')
        AVAIL_DISK=$(df -h / | awk 'NR==2 {print $4}')
        DISK_USED_PCT=$(df -h / | awk 'NR==2 {print $5}')
        
        echo "    \"total\": \"$TOTAL_DISK\"," >> $OUTPUT_FILE
        echo "    \"available\": \"$AVAIL_DISK\"," >> $OUTPUT_FILE
        echo "    \"used_percent\": \"$DISK_USED_PCT\"" >> $OUTPUT_FILE
    else
        echo "    \"total\": \"Unknown\"," >> $OUTPUT_FILE
        echo "    \"available\": \"Unknown\"," >> $OUTPUT_FILE
        echo "    \"used_percent\": \"Unknown\"" >> $OUTPUT_FILE
    fi
else
    echo "    \"total\": \"Unknown\"," >> $OUTPUT_FILE
    echo "    \"available\": \"Unknown\"," >> $OUTPUT_FILE
    echo "    \"used_percent\": \"Unknown\"" >> $OUTPUT_FILE
fi

echo "  }," >> $OUTPUT_FILE

# Get network information
echo "  \"network\": {" >> $OUTPUT_FILE

# Get primary IP address (non-loopback)
if [ "$OS_TYPE" = "Linux" ]; then
    if command_exists ip; then
        PRIMARY_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
    elif command_exists ifconfig; then
        PRIMARY_IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
    else
        PRIMARY_IP="Unknown"
    fi
elif [ "$OS_TYPE" = "Darwin" ]; then
    if command_exists ifconfig; then
        PRIMARY_IP=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
    else
        PRIMARY_IP="Unknown"
    fi
else
    PRIMARY_IP="Unknown"
fi

echo "    \"primary_ip\": \"$PRIMARY_IP\"" >> $OUTPUT_FILE
echo "  }" >> $OUTPUT_FILE

# Close the main JSON object
echo "}" >> $OUTPUT_FILE

# Make the file pretty (if jq is available)
if command_exists jq; then
    jq . $OUTPUT_FILE > ${OUTPUT_FILE}.tmp && mv ${OUTPUT_FILE}.tmp $OUTPUT_FILE
fi

echo "Hardware specifications have been saved to $OUTPUT_FILE"

