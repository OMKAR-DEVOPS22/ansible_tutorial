#!/bin/bash

# Get partition information
partitions=$(df -h --output=source,avail | tail -n +2)

# Iterate through partitions
while IFS= read -r line; do
  partition=$(echo "$line" | awk '{print $1}')
  available_space=$(echo "$line" | awk '{print $2}')

  # Extract numerical value and unit from available space
  value=$(echo "$available_space" | sed 's/[^0-9.]*//g')
  unit=$(echo "$available_space" | sed 's/[0-9.]*//g')

  # Convert units to a common unit (e.g., GB)
  case "$unit" in
    G|Gi) factor=1 ;;
    M|Mi) factor=0.001 ;;
    K|Ki) factor=0.000001 ;;
    *) continue ;;
  esac

  # Calculate available space in GB
  available_gb=$(echo "$value * $factor" | bc)

  # Check if available space is less than 6GB
  if (( $(echo "$available_gb < 6" | bc -l) )); then
    echo "Partition $partition has available space less than 6GB: ${available_gb}GB"
  fi
done <<< "$partitions"
