# HoneywareX

![honeywarex](https://github.com/Cyboghostginx/HoneywareX/blob/main/logo.png)

HoneywareX is a PoC shell-based honeypot motivated by Cowrie, and the "LLM in the shell" paper (Sladic et al., 2024). My master's project looks into building on existing research in the field of honeypots in cybersecurity. I'm looking into how to leverage RAG to enhance dynamic ability in Linux shell honeypots.

Traditional static Unix honeypots like Cowrie lack the dynamic abilities needed in real-life scenarios when engaging attackers during SSH access, such as lack of access to different network utilities commands like ping. I aim to increase the realism of this project by implementing other impressive abilities, and also make it easier for anyone to just test out on any system in just a few commands’ execution.

To improve speed, the commands are classified into 3 part namely:
- Native Commands: This commands can work without RAG intervention, mostly file management.
- Non-Native Commands: These commands needs RAG intervention.
- Invalid Commands: Any command that can't be found in a commands.txt file will be rendered invalid and would retun the command not found error instead of processing an invalid command which would introduce hallucination in RAG or induce more resource usage in our honeypot.

---

## Features

- **AI-Driven Simulation**: Uses both the static and RAG ability to emulate common SSH commands and responses for a realistic experience.
- **Logging and Monitoring**: Tracks user activity, including commands executed and session details. Also, allows the logged information to be viewed in a simple one page frontend.
- **Lightweight Deployment**: Simple setup and low system requirements make it easy to deploy.
- **Other Utilities**: Implemetation of 3 commands system (AI required, AI not required, and Invalid) which helps to increase speed in the honeypot responses by automatically adapting to when AI is needed or not.

---

## Requirements
- **AI Host**: This is where our model(s) from [Ollama](https://ollama.com/library) to be used will be hosted. You can rent a GPU on the server or use your local machine. At least 16 GB of RAM is required.
- **Client Host**: This is where to access the ssh and test out the honeypot

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Cyboghostginx/HoneywareX.git
   cd HoneywareX

2. Start AI and Tunelling Server:
   ```bash
   sudo bash ai_server.sh
***Note: The tunnelling part of this script is only required to use NGROK to port out Ollama's 11434 port from any server we would like to host our models. Lightweight models up to 8B can easily be hosted on your local computer with 16GB RAM. Whatever link you have concluded to be for your Ollama, either http://localhost:11434 or any link from external server should go into config.py***

3. Launch Work:
   ```bash
   python3 main.py

---

## Acknowledgement
I'm acknowledging entity/softwares used throughout this project, and are down below:
- Cowrie: I'm are reworking the logic from Cowrie in this project. Cowrie is a static shell honeypot which means that AI is not required resulting in lack of dynamic ability for certain commands.
- Paramiko: Paramiko has been used in this project for the network level implementation to allow SSH access into the honeypot system.
- Llamaindex: Llamaindex framework has been used for the implementation of RAG into this honeypot.
- Ollama: This is a library of different open-source models that can easily be used on port 11434 after ollama installation.

---

## Conclusion
This work is a PoC for my cureent master's project "Leveraging RAG-Based Prompt Engineering for Low-Interaction Network Honeypots"


