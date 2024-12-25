export ftp_proxy=ftp://proxy-dmz.intel.com:912
export https_proxy=http://proxy-dmz.intel.com:912
export socks_proxy=socks://proxy-dmz.intel.com:912
export http_proxy=http://proxy-dmz.intel.com:912
GITHUB_TOKEN=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 /home/eikan/miniforge3/envs/pyt-xpu/bin/python3 /home/eikan/local_disk/ai_tools/highlight_github_activities.py --send-email --interval 4 > /home/eikan/local_disk/ai_tools/highlight_github_activities.log 2>&1