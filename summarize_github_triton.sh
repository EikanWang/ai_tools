export ftp_proxy=ftp://proxy-dmz.intel.com:912
export https_proxy=http://proxy-dmz.intel.com:912
export socks_proxy=socks://proxy-dmz.intel.com:912
export http_proxy=http://proxy-dmz.intel.com:912
GITHUB_TOKEN=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 OPENAI_API_KEY=sk-88a0ec85b2d9426093ddfb6fca093b4a /home/eikan/miniforge3/envs/pyt-xpu/bin/python3 /home/eikan/local_disk/ai_tools/summarize_github.py --combine-summaries --send-email --owner triton-lang --repo triton > /home/eikan/local_disk/ai_tools/summarize_github_triton.log 2>&1
