# HoneywareX

![A cute cat](https://github.com/Cyboghostginx/HoneywareX/blob/main/logo.png)

HoneywareX is a PoC shell-based honeypot highly motivated by Cowrie, and the "LLM in the shell" paper (Sladic et al., 2024). My master's project looks into building on existing research in the field of honeypots in cybersecurity. I'm looking into how to leverage RAG to enhance dynamic ability in Linux shell honeypots.

Traditional static Unix honeypots like Cowrie lack the dynamic abilities needed in real-life scenarios when engaging attackers during SSH access, such as lack of access to different network utilities commands like ping. I aim to increase the realism of this project by implementing other impressive abilities, and also make it easier for anyone to just test out on any system in just a few commands’ execution.

To improve speed, the commands are classified into 3 part namely:
- Native Commands: This commands can work without RAG intervention, mostly file management.
- Non-Native Commands: These commands needs RAG intervention.
- Invalid Commands: Any command that can't be found in a commands.txt file will be rendered invalid and would retun the comman not found instead of processing an invalid command which would introduce more resource usage in our honeypot.

---

## Features

- **AI-Driven Simulation**: Uses AI to emulate common SSH commands and responses for a realistic experience.
- **Low-Interaction Design**: Focuses on lightweight emulation to minimize resource usage while effectively capturing interactions.
- **Logging and Monitoring**: Tracks user activity, including commands executed and session details. Also, allows the logged information to be viewed in a simple one page frontend.
- **Lightweight Deployment**: Simple setup and low system requirements make it easy to deploy.
- **Other Utilities**: Implemetation of 2 commands system (AI required or AI not required) which helps to increase speed in the honeypot responses by automatically adapting to when AI is needed or not.

---

## Requirements
- **AI Host**: This is where our model(s) from [Ollama](https://ollama.com/library) to be used will be hosted. You can rent a GPU on the server or use your local machine. At least 16 GB of RAM is required.
- **Client Host**: This is where to access the ssh and test out the honeypot

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/HoneywareX.git
   cd HoneywareX

2. Start AI and Tunelling Server:
   ```bash
   sudo bash ai_server.sh
[^1]: This is the footnote.

Note: The tunnelling part of this script is only required to use NGROK to port out Ollama's 11434 port from any server we would like to host our models. Lightweight models up to 8B can easily be hosted on your local computer with 16GB RAM.

3. Start AI and Tunelling Server:
   ```bash
   sudo bash ai_server.sh


