#!/bin/bash

echo "Installing performance test dependencies..."

# Install main project requirements
pip install -r requirements.txt

echo "All dependencies installed successfully!"
echo "You can now run the performance test application with:"
echo "  ./run_webapp.sh" 