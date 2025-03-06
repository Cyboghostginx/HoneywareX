# HoneywareX

![honeywarex](https://github.com/Cyboghostginx/HoneywareX/blob/main/assets/logo.png)

HoneywareX is a PoC shell-based honeypot motivated by Cowrie, and the "LLM in the shell" paper (Sladic et al., 2024). My master's project looks into building on existing research in the field of honeypots in cybersecurity. I'm looking into how to leverage RAG to enhance dynamic ability in Linux shell honeypots.

Traditional static Unix honeypots like Cowrie lacks the dynamic abilities needed in real-life scenarios when engaging attackers during SSH access due to its static nature, amongst are lack of access to different network utilities commands like netcat, netstat etc. I aim to increase the realism of this project by implementing other impressive abilities, and also make it easier for anyone to just test out on any system in just a few commands’ execution. But most importantly, the purpose of this thesis is to evaluate if RAG can increase context awareness for honeypot such as this shell-based honeypot, which means that my independent work is mostly the RAG folder and the other connection between the classes, and function.

***NB: It is also important to note that Copilot AI in VScode has been thoroughly used throughout this project for the reworking of the static honeypot logic from Cowrie, and also to add few additional features because of little time left to submit my paper, and also the complexity of that area of this project. My own work only focused on the implementation of RAG using Llamaindex and Ollama. (:***

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
- At least 16gb ram system (the higher the faster)
- that's all...(:

---

## Installation

1. Clone the repository:
   Ensure to download Ollama from [here](https://ollama.com/download/linux), you can type in "ollama" in your terminal to see it it has been correctly installed.
   
   ```bash
   ollama pull Cyboghost/llama-linux
   git clone https://github.com/Cyboghostginx/HoneywareX.git
   cd HoneywareX
   pip install -r requirements.txt
   ```
   
   ***Or (OPTIONALLY) if you want to host the model on an external GPU server, you can use run ai_server.sh script in that server to install it on that server and it will also automatically tunnel out the      port (11434) where the Ollama model is hosted. Note: The tunnelling part of this script is only required to use NGROK to port out Ollama's 11434 port from any server we would like to host our models.        Lightweight models up to 8B can easily be hosted on your local computer with 16GB RAM. Whatever link you have concluded to be for your Ollama, either http://localhost:11434 or any link from external         server will go into config.py***

   ```bash
   sudo bash ai_server.sh
   ```
   

2. Launch Work:
   
   ```bash
   python3 main.py
   ```

3. Get into the provided SSH Access Honeypot:
   ```bash
   ssh honeypot@{ip_provided} -p 2222
   ```
4. Then you can always view the logged information by firing up the index.html file in the frontend folder

---

## Common errors
If you are having issues with python, ensure you have python 11, and also ensure pip is using python 11

---

## Acknowledgement
I'm acknowledging entity/softwares used throughout this project, and are listed below:
- [Cowrie](https://github.com/cowrie/cowrie): I have reworked the logic from Cowrie in this project. Cowrie is a static shell honeypot which means that AI is not required resulting in lack of dynamic ability for certain commands.
- [Paramiko](https://www.paramiko.org/): Paramiko has been used in this project for the network level implementation to allow SSH access into the honeypot system.
- [LlamaIndex](https://docs.llamaindex.ai/en/stable/): Llamaindex framework has been used for the implementation of RAG into this honeypot.
- [Ollama](https://ollama.com/library): This is a library of different open-source models that can easily be used on port 11434 after ollama installation.
- Copilot AI used inside VScode for debugging

---

## Future Work
This project will further look into native commands that are yet to be implemented, and also refine the AI implementation method. Maybe full finetuning of a model could better enhance the dynamic ability of this honeypot.

---

## Conclusion
This work is still subject to future changes as new discoveries or errors are being detected from testing. AI has been used extensively for the reworking of Cowrie's logic for simpler execution and easy use.


