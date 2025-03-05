#! /bin/bash

# Models tested in this project (Open-Source)
# -
# Llama 3.2 - 3B (ollama pull 3.2:3b) - 
# Qwen 2.5 - 3B (ollama pull qwen2.5:3b) - 
# -
# Dolphin3 - 8B (ollama pull dolphin3) - 
# Llama-linux - 8B (ollama pull Cyboghost/llama-linux) - Tuned by me specifically for this project
# Llama3.1 - 8B (ollama run llama3.1) - 
# Gemma - 9B (ollama pull gemma2:latest) - 


# this script can be used to setup our AI server equiped with the baseline models needed, and also with an NGROK tunneling that allows us to use this model on any other project.

# install Ollama
apt update && apt -y install curl wget jq cron && curl -fsSL https://ollama.com/install.sh | sh
nohup ollama start &
sleep 3
echo -e "\n"

# Pull Ollama's models needed from repository
ollama pull Cyboghost/llama-linux # any Model to be used can be changed here
sleep 3
# We can start with these 2 model for testing and add on later.

# cron job for ollama run llama3.2 ""
(crontab -l 2>/dev/null; echo '*/5 * * * * ollama run Cyboghost/llama-linux""') | crontab -

# install NGROK
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | tee /etc/apt/sources.list.d/ngrok.list \
  && apt update \
  && apt install ngrok

# configure Ngrok
ngrok config add-authtoken 2qLsPVOpFTwyh61s6XD2aJh1iRT_6LBBmpHsJ5PUmrqJnQ4Ag # This is a just free NGROK token, nothing personal (:

# get Ngrok Link from port 11434 that Ollama usually runs on
ngrok http 11434 --host-header="localhost:11434" --log=stdout >/dev/null & sleep 3 && echo -e "\n" && echo "You can use this link for your Ollama model's inference anywhere in the world" && curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url'
