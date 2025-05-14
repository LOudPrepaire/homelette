#!/bin/bash
set -e

echo "Starting the model server..."

# Define the key for Modeller
KEY_MODELLER="MODELIRANJE"

# Path to the Modeller config file
CONFIG_FILE="/opt/conda/lib/modeller-10.6/modlib/modeller/config.py"

# Check if the config file exists
if [[ -f "$CONFIG_FILE" ]]; then
    sed -i "s/XXXX/${KEY_MODELLER}/" "$CONFIG_FILE"
else
    echo "Error: Modeller config.py not found." >&2
    exit 1
fi


echo "Environment vars:"
env | grep -E 'INPUT|OUTPUT|BUCKET'

python3 app.py "$INPUT" "$OUTPUT" "$BUCKET" 
