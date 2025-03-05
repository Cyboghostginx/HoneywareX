#! /bin/bash

# Models we can test in this project, many more in Ollama library (Open-Source)
# -
# TinyLlama - 1.1B (ollama pull tinyllama) - ❌
# Gemma - 2B (ollama pull gemma:2b) - ✅
# Llama 3.2 - 3B (ollama pull 3.2:3b) - ✅
# Qwen 2.5 - 3B (ollama pull qwen2.5:3b) - ✅
# -
# Dolphin3 - 8B (ollama pull dolphin3) - 
# Llama3 - 8B (ollama pull llama3) - 
# Gemma - 9B (ollama pull gemma2:latest) - 
# Zephyr - 7B (ollama pull zephyr) - 
# Phi-4 - 14b (ollama pull phi4) - 


# This script can be used to setup our AI server equiped with the baseline models needed, and also with an NGROK tunneling that allows us to use this model on any other project.

# Install Ollama
apt update && apt -y install curl wget jq cron && curl -fsSL https://ollama.com/install.sh | sh
nohup ollama start &
sleep 3
echo -e "\n"

# Pull Ollama's models needed from repository
ollama pull llama3.2:3b # any Model to be used can be changed here
sleep 3
# We can start with these 2 model for testing and add on later.

# cron job for ollama run llama3.2 ""
(crontab -l 2>/dev/null; echo '*/5 * * * * ollama run llama3.2""') | crontab -

# Install NGROK
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | tee /etc/apt/sources.list.d/ngrok.list \
  && apt update \
  && apt install ngrok

# Configure Ngrok
ngrok config add-authtoken 2qLsPVOpFTwyh61s6XD2aJh1iRT_6LBBmpHsJ5PUmrqJnQ4Ag # This is a just free NGROK token, nothing personal (:

# Get Ngrok Link from port 11434 that Ollama usually runs on
ngrok http 11434 --host-header="localhost:11434" --log=stdout >/dev/null & sleep 3 && echo -e "\n" && curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'
