# HoneywareX

HoneywareX is a shell-based honeypot highly motivated by Cowrie, and the "LLM in the shell" paper (Sladic et al., 2024). My master's project looks into building on existing research in the field of honeypots in cybersecurity. I'm looking into how we can leverage RAG to enhance dynamic ability in Linux shell honeypots.

Traditional static Unix honeypots like Cowrie lack the dynamic abilities needed in real-life scenarios when engaging attackers during SSH access, such as lack of access to different network utilities commands like ping. I aim to increase the realism of this project by implementing other impressive abilities, and also make it easier for anyone to just test out on their system in just a few commands’ execution.

---

## Features

- **AI-Driven Simulation**: Uses AI to emulate common SSH commands and responses for a realistic experience.
- **Low-Interaction Design**: Focuses on lightweight emulation to minimize resource usage while effectively capturing interactions.
- **Logging and Monitoring**: Tracks user activity, including commands executed and session details. Also, allows the logged information to be viewed in a simple one page frontend.
- **Lightweight Deployment**: Simple setup and low system requirements make it easy to deploy.
- **Other Utilities**: Implemetation of 2 commands system (AI required or AI not required) which helps to increase speed in the honeypot responses by automatically adapting to when AI is needed or not.

---
[Wan2.1](https://github.com/Wan-Video/Wan2.1)
## Requirements
- **AI Host**: This is where our model(s) from [Ollama](https://ollama.com/library) to be used will be hosted.
- **Low-Interaction Design**: Focuses on lightweight emulation to minimize resource usage while effectively capturing interactions.

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/HoneywareX.git
   cd HoneywareX

2. Start AI and Tunelling Server:
   ```bash
   sudo bash ai_server.sh


