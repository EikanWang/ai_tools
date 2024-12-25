export ftp_proxy=ftp://proxy-dmz.intel.com:912
export https_proxy=http://proxy-dmz.intel.com:912
export socks_proxy=socks://proxy-dmz.intel.com:912
export http_proxy=http://proxy-dmz.intel.com:912
GITHUB_TOKEN=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 OPENAI_API_KEY=sk-e5bdff8f951a42028676fc61a349e13c /home/eikan/miniforge3/envs/pyt-xpu/bin/python3 /home/eikan/local_disk/ai_tools/summarize_github.py --combine-summaries --send-email --owner flashinfer-ai --repo flashinfer > /home/eikan/local_disk/ai_tools/summarize_github_flashinfer.log 2>&1
