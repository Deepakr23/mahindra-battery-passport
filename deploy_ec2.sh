#!/usr/bin/env bash
# ==============================================================================
# AWS EC2 UBUNTU DEPLOYMENT SCRIPT - MAHINDRA BATTERY PASSPORT
# ==============================================================================
# Run this script on your EC2 instance to install Docker, build the container,
# and launch the web server on port 80.
# ==============================================================================

set -e

echo "=== 1. Updating System Packages ==="
sudo apt-get update
sudo apt-get upgrade -y

echo "=== 2. Installing Docker Engine ==="
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --yes --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Ensure current user can run docker without sudo
sudo usermod -aG docker $USER

echo "=== 3. Building Mahindra Battery Passport Docker Image ==="
# Stops previous instances if they exist
sudo docker stop battery-passport || true
sudo docker rm battery-passport || true

# Build docker container
sudo docker build -t mahindra-battery-passport .

echo "=== 4. Starting Container Service on Port 80 ==="
# Runs the container, maps it to host port 80, and restarts automatically on reboot
sudo docker run -d \
  --name battery-passport \
  -p 80:80 \
  --restart always \
  mahindra-battery-passport

echo "=============================================================================="
echo "DEPLOYMENT COMPLETE!"
echo "Your server is now running as a background service on port 80."
echo "=============================================================================="
echo "IMPORTANT SECURITY STEP:"
echo "Please go to your AWS EC2 Console -> Security Groups."
echo "Add an INBOUND RULE to allow TCP traffic on Port 80 (HTTP) from 'Any-IPv4' (0.0.0.0/0)"
echo "so your ESP32 hardware and web browsers can access the app!"
echo "=============================================================================="
