# HoneywareX

![honeywarex](https://github.com/Cyboghostginx/HoneywareX/blob/main/logo.png)

HoneywareX is a PoC shell-based honeypot motivated by Cowrie, and the "LLM in the shell" paper (Sladic et al., 2024). My master's project looks into building on existing research in the field of honeypots in cybersecurity. I'm looking into how to leverage RAG to enhance dynamic ability in Linux shell honeypots.

Traditional static Unix honeypots like Cowrie lack the dynamic abilities needed in real-life scenarios when engaging attackers during SSH access, such as lack of access to different network utilities commands like ping. I aim to increase the realism of this project by implementing other impressive abilities, and also make it easier for anyone to just test out on any system in just a few commands’ execution.

***NB: It is also important to note that Copilot AI in VScode has been thoroughly used throughout this project for the reworking of the static honeypot logic from Cowrie, and also to add few additional features because of time, and also the complexity of that area of this project. My own work only focused on the implementation of RAG using Llamaindex and Ollama. (:***

To improve speed, the commands are classified into 3 parts namely:
- Native Commands: These commands can work without RAG intervention, mostly file management.
- Non-Native Commands: These commands need RAG intervention.
- Invalid Commands: Any command that can't be found in a commands.txt file will be rendered invalid and would return the command not found error instead of processing an invalid command which would introduce hallucination in RAG or induce more resource usage in our honeypot.

---

## Features

- **AI-Driven Simulation**: Uses both the static and RAG ability to emulate common SSH commands and responses for a realistic experience.
- **Logging and Monitoring**: Tracks user activity, including commands executed and session details. Also, allows the logged information to be viewed in a simple one-page frontend.
- **Lightweight Deployment**: Simple setup and low system requirements make it easy to deploy.
- **Other Utilities**: Implementation of 3 commands systems (AI required, AI not required, and Invalid) which helps to increase speed in the honeypot responses by automatically adapting to when AI is needed or not.

---

## Requirements
- **AI Host**: This is where our model(s) from [Ollama](https://ollama.com/library) to be used will be hosted. You can rent a GPU on the server or use your local machine. At least 16 GB of RAM is required. Also, ensure that you have properly installed Ollama as required from [here](https://ollama.com/download/linux) and pulled the necessary model you might wish to use, but for this project, we have stuck to llama3.2:3b for fast inferencing: To install any model in terminal use "ollama pull {model}". A file ai_server.sh has also been attached for easy installation on Linux. You can open it and put the model you might need. Also, it is able to use NGROK to tunnel out the port 11434 from any server you have decided to host the model.
- **Client Host**: This is where you can access the SSH and test out the honeypot.

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Cyboghostginx/HoneywareX.git
   cd HoneywareX

2. Start AI and Tunelling Server:
   ```bash
   sudo bash ai_server.sh
***Note: The tunnelling part of this script is only required to use NGROK to port out Ollama's 11434 port from any server we would like to host our models. Lightweight models up to 8B can easily be hosted on your local computer with 16GB RAM. Whatever link you have concluded to be for your Ollama, either http://localhost:11434 or any link from external server will go into config.py***

3. Launch Work:
   ```bash
   python3 main.py

4. Get into the provided SSH Access Honeypot:
   ```bash
   ssh honeypot@{ip_provided} -p 2222

---

## Acknowledgement
I'm acknowledging entity/softwares used throughout this project, and are down below:
- Cowrie: I'm are reworking the logic from Cowrie in this project. Cowrie is a static shell honeypot which means that AI is not required resulting in lack of dynamic ability for certain commands.
- Paramiko: Paramiko has been used in this project for the network level implementation to allow SSH access into the honeypot system.
- Llamaindex: Llamaindex framework has been used for the implementation of RAG into this honeypot.
- Ollama: This is a library of different open-source models that can easily be used on port 11434 after ollama installation.

---

## Conclusion
This work is still subjected to future changes as new discovery or errors are being detected from testing. AI has been used for the reworking of Cowrie's logic for simpler execution, and easy use.


