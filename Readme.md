# HoneywareX

HoneywareX is a shell-based honeypot highly motivated by Cowrie, and "LLM in the shell" paper (Sladic et al., 2024). My master's project looks into building on existing researches in the field of honeypot in cybersecurity. I'm looking into how we can leverage RAG to enhance dynamic ability in Linux shell honeypot.

---

## Features

- **AI-Driven Simulation**: Uses AI to emulate common SSH commands and responses for a realistic experience.
- **Low-Interaction Design**: Focuses on lightweight emulation to minimize resource usage while effectively capturing interactions.
- **Logging and Monitoring**: Tracks user activity, including commands executed and session details.
- **Lightweight Deployment**: Simple setup and low system requirements make it easy to deploy.

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/HoneywareX.git
   cd HoneywareX

2. Start AI and Tunelling Server:
   ```bash
   sudo bash ai_server.sh
