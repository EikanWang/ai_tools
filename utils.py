# Read token.json file and return the github token and chat_llm token
#  1. The token.json file should be in the same directory as this file
#  2. The token.json file should have the following format:
#    {
#      "GITHUB_TOKEN": "xxx",
#      "DEEPSEEK_API_KEY": "xxx",
#      "OPENAI_API_KEY": "xxx"
#    }
#  3. If token.json file is not found, all tokens will be get from the environment variables

import json
import os

def get_tokens():
    # Get the path to the token.json file
    path = os.path.join(os.path.dirname(__file__), 'token_config.json')

    # If the file does not exist, return the environment variables
    if not os.path.exists(path):
        return os.environ.get('GITHUB_TOKEN'), os.environ.get('DEEPSEEK_API_KEY'), os.environ.get('OPENAI_API_KEY')

    # Read the file
    with open(path, 'r') as file:
        data = json.load(file)

    # Return the tokens
    return data.get('GITHUB_TOKEN'), data.get('DEEPSEEK_API_KEY'), data.get('OPENAI_API_KEY')
