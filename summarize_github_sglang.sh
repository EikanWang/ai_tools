export ftp_proxy=ftp://proxy-dmz.intel.com:912
export https_proxy=http://proxy-dmz.intel.com:912
export socks_proxy=socks://proxy-dmz.intel.com:912
export http_proxy=http://proxy-dmz.intel.com:912
GITHUB_TOKEN=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 OPENAI_API_KEY=sk-45d50fff73ce424a92451fbb4c4cfe60 /home/eikan/miniforge3/envs/pyt-xpu/bin/python3 /home/eikan/local_disk/ai_tools/summarize_github.py --combine-summaries --send-email --owner sgl-project --repo sglang > /home/eikan/local_disk/ai_tools/summarize_github_sglang.log 2>&1
