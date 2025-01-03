import sys
from github import Github
from datetime import datetime
import os
import argparse
import shelve
import logging
from dotenv import load_dotenv
import openai
import tiktoken
import sqlite3

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from mail_util import send_email_with_attachment
from utils import get_tokens

load_dotenv()

logger = logging.getLogger(__name__)

llm_keys = {
    "OpenAI" : "OPENAI_API_KEY",
    "DeepSeek" : "DEEPSEEK_API_KEY"
}

llm_urls = {
    "OpenAI" : "https://api.openai.com",
    "DeepSeek" : "https://api.deepseek.com"
}

ignored_authors = {"pytorchmergebot", "pytorch-bot[bot]", "facebook-github-bot"}

def init_db(db_path):
    """
    Initialize the database.
    """
    return sqlite3.connect(db_path)

def count_tokens(text, encoding_name='gpt2'):
    """
    Counts the number of tokens in a text string using the specified encoding.
    """
    logger.info(f"Counting tokens for text: {text[:50]}...")
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text, disallowed_special=())
    logger.info(f"Token count: {len(tokens)}")
    return len(tokens)

def summarize_chunk(client, chunk, prompt_instructions="", max_summary_tokens=None):
    logger.info(f"Summarizing chunk: {chunk[:50]}...")
    prompt = f"{prompt_instructions}{chunk}"
    try:
        response = client.chat.completions.create(
            model='deepseek-chat',  # You can switch to 'gpt-4' if you have access
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=max_summary_tokens,
            temperature=0.7,
        )
        summary = response.choices[0].message.content.strip()
        logger.info(f"Summary generated: {summary[:50]}...")
        return summary
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return ""

def text_summarize(text_chunks, serving = "DeepSeek", instruction=None, context=None, separator="\n"):
    _, deep_seek_api_key, openai_api_key = get_tokens()
    api_key = openai_api_key if serving == "OpenAI" else deep_seek_api_key
    client = openai.OpenAI(api_key=api_key, base_url=llm_urls[serving])
    if instruction is None:
        instruction = "Summarize the text below:\n\n"
    max_tokens = 32000 * 2  # 64K tokens
    instruction_num_tokens = count_tokens(instruction)
    chunk_num_tokens = [count_tokens(chunk) for chunk in text_chunks]
    end_id = 0
    summaries = []
    while end_id < len(chunk_num_tokens):
        num_tokens = instruction_num_tokens
        start_id = end_id
        while num_tokens < max_tokens and end_id < len(chunk_num_tokens):
            num_tokens += chunk_num_tokens[end_id]
            end_id += 1
        assert end_id > start_id
        if num_tokens > max_tokens:
            logger.warning(f"Chunk {start_id} is too large to fit in the max_tokens={max_tokens} limit.")
            text = text_chunks[start_id][:max_tokens - instruction_num_tokens]
        else:
            text = separator.join(text_chunks[start_id:end_id])
        summary = summarize_chunk(client, text, instruction)
        summaries.append(summary)
    return summaries

class GitHubItem:
    def __init__(self, number, title, url, description, submitter, tags, assignees, reviewers, created_at, comments, review_comments, state):
        self.number = number
        self.title = title
        self.url = url
        self.description = description
        self.submitter = submitter
        self.tags = tags
        self.assignees = assignees
        self.reviewers = reviewers
        self.created_at = created_at
        self.comments = comments
        self.review_comments = review_comments
        self.state = state

    def __str__(self):
        return (
            f"Number: {self.number}\n"
            f"Title: {self.title}\n"
            f"URL: {self.url}\n"
            f"Description: {self.description}\n"
            f"Submitter: {self.submitter}\n"
            f"Tags: {', '.join(self.tags)}\n"
            f"Assignees: {', '.join(self.assignees)}\n"
            f"Reviewers: {', '.join(self.reviewers)}\n"
            f"Created At: {self.created_at}\n"
            f"State: {self.state}\n"
            f"Comments: {len(self.comments)}\n"
            f"Review Comments: {len(self.review_comments)}"
        )

    def full_str(self, need_comments=True):
        if need_comments:
            comments_str = "\n".join(
                [f"- Comment by {comment['author']} (Created at {comment['created_at']}): {comment['body']}" for comment in self.comments]
            )
            review_comments_str = "\n".join(
                [f"- Review Comment by {review_comment['author']} (Created at {review_comment['created_at']}): {review_comment['body']}" for review_comment in self.review_comments]
            )
            return "\n".join([str(self), comments_str, review_comments_str])
        else:
            return str(self)

class GitHubItemDB:
    def __init__(self, org, repo) -> None:
        self._db_path = f"{org}_{repo}.db"

    def __enter__(self):
        self._db = sqlite3.connect(self._db_path)
        self._cursor = self._db.cursor()
        self._cursor.execute('''
            CREATE TABLE IF NOT EXISTS github_items (
                number TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                description TEXT,
                submitter TEXT,
                tags TEXT,
                assignees TEXT,
                reviewers TEXT,
                created_at TEXT,
                comments TEXT,
                review_comments TEXT,
                state TEXT
            )
        ''')
        return self

    def __getitem__(self, key):
        cursor = self._db.cursor()
        cursor.execute('SELECT * FROM github_items WHERE number = ?', (key,))
        row = cursor.fetchone()
        if not row:
            raise KeyError(key)
        return GitHubItem(*row)

    def __setitem__(self, github_item: GitHubItem):
        cursor = self._db.cursor()
        cursor.execute('''
            INSERT INTO github_items (number, title, url, description, submitter, tags, assignees, reviewers, created_at, comments, review_comments, state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (github_item.number, github_item.title, github_item.url, github_item.description, github_item.submitter, github_item.tags, github_item.assignees, github_item.reviewers, github_item.created_at, github_item.comments, github_item.review_comments, github_item.state))
        self._db.commit()

    def __delitem__(self, key):
        cursor = self._db.cursor()
        cursor.execute('DELETE FROM github_items WHERE number = ?', (key,))
        self._db.commit()

    def __iter__(self):
        cursor = self._db.cursor()
        cursor.execute('SELECT * FROM github_items')
        # Fetch all items and convert each item to github item and then return the iterator
        return iter([GitHubItem(*row[1:]) for row in cursor.fetchall()])

    def __exit__(self, exc_type, exc_value, traceback):
        self._db.close()

def refresh_items(repo, start_date, end_date, db):
    start_date_dt = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ")
    end_date_dt = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ")
    all_issues = repo.get_issues(state='all', since=start_date_dt)
    for item in all_issues:
        if item.created_at.replace(tzinfo=None) > end_date_dt:
            logger.info("Reached items outside of date range. Stopping early.")
            break
        if str(item.number) in db:
            logger.info(f"Item with ID {item.id} found in database, updating fields except comments.")
            github_item = db[str(item.number)]
            github_item.title = item.title
            github_item.description = item.body if item.body else "No description available"
            github_item.tags = [label.name for label in item.labels]
            github_item.assignees = [assignee.login for assignee in item.assignees]
            github_item.reviewers = []
            github_item.state = item.state
            # commented out for efficiency
            if '/pull/' in item.html_url:  # To distinguish pull requests by URL pattern
                pr = repo.get_pull(item.number)
                github_item.reviewers = list(set([review.user.login for review in pr.get_reviews() if review.user]))
            db[str(item.number)] = github_item
            continue
        process_item(repo, item, db)

def refresh_item_comments(repo, start_date, db):
    start_date_dt = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ")
    # Fetch issue comments
    for comment in repo.get_issues_comments(since=start_date_dt):
        item_id = comment.issue_url.split('/')[-1]
        if item_id in db:
            update_with_new_comment(db, item_id, comment, is_review=False)
        else:
            item = repo.get_issue(int(item_id))
            process_item(repo, item, db)

    # Fetch pull request comments
    for comment in repo.get_pulls_comments(since=start_date_dt):
        item_id = comment.pull_request_url.split('/')[-1]
        if item_id in db:
            update_with_new_comment(db, item_id, comment, is_review=False)
        else:
            item = repo.get_pull(int(item_id))
            process_item(repo, item, db)

    # Fetch pull request review comments
    for comment in repo.get_pulls_review_comments(since=start_date_dt):
        item_id = comment.pull_request_url.split('/')[-1]
        if item_id in db:
            update_with_new_comment(db, item_id, comment, is_review=True)
        else:
            item = repo.get_pull(int(item_id))
            process_item(repo, item, db)

def update_with_new_comment(db, item_id, comment, is_review):
    github_item = db[item_id]
    new_comment = {
        "author": comment.user.login,
        "body": comment.body,
        "created_at": comment.created_at.isoformat()
    }
    # Check if the comment already exists
    existing_comments = github_item.review_comments if is_review else github_item.comments
    if any(c["created_at"] == new_comment["created_at"] and c["author"] == new_comment["author"] for c in existing_comments):
        logger.info(f"Comment by {new_comment['author']} on {new_comment['created_at']} already exists, skipping.")
        return

    if is_review:
        github_item.review_comments.append(new_comment)
    else:
        github_item.comments.append(new_comment)
    db[item_id] = github_item

def process_item(repo, item, db):
    logger.info(f"Starting to process item '{item.title}' with ID {item.number}")
    created_at = item.created_at.isoformat()
    comments = []
    review_comments = []

    # Fetch normal comments
    for comment in item.get_comments():
        logger.info(f"Fetching comment by {comment.user.login} created at {comment.created_at.isoformat()}")
        comments.append({
            "author": comment.user.login,
            "body": comment.body,
            "created_at": comment.created_at.isoformat()
        })

    # Fetch review comments for pull requests
    if '/pull/' in item.html_url:  # To distinguish pull requests by URL pattern
        pr = repo.get_pull(item.number)
        for review_comment in pr.get_review_comments():
            logger.info(f"Fetching review comment by {review_comment.user.login} created at {review_comment.created_at.isoformat()}")
            review_comments.append({
                "author": review_comment.user.login,
                "body": review_comment.body,
                "created_at": review_comment.created_at.isoformat()
            })

    description = item.body if item.body else "No description available"
    submitter = item.user.login if item.user else "Unknown"
    tags = [label.name for label in item.labels]
    assignees = [assignee.login for assignee in item.assignees]
    reviewers = []
    state = item.state

    if '/pull/' in item.html_url:  # To distinguish pull requests by URL pattern
        reviewers = list(set([review.user.login for review in pr.get_reviews() if review.user]))
        logger.info(f"Fetching reviewers for PR #{item.number}: {', '.join(reviewers)}")

    logger.info(f"Adding or updating item '{item.title}' created by {submitter} on {created_at}")
    github_item = GitHubItem(
        item.number,
        item.title,
        item.html_url,
        description,
        submitter,
        tags,
        assignees,
        reviewers,
        created_at,
        comments,
        review_comments,
        state
    )
    db[str(item.number)] = github_item

def load_db(db_path):
    """
    Load the GitHub items from the database.
    """
    with shelve.open(db_path) as db:
        items = list(db.values())
    return items

def filter_items(items, rules):
    """
    Apply filtering rules to the list of GitHub items.
    """
    filtered_items = []
    for item in items:
        if apply_rules(item, rules):
            filtered_items.append(item)
    return filtered_items

def apply_rules(item: GitHubItem, rules):
    """
    Check if a GitHub item satisfies the given filtering rules.
    """
    # Rule 1: Filter by start and end dates
    created_at = datetime.fromisoformat(item.created_at.replace('Z', '+00:00')).replace(tzinfo=None)
    comment_dates = [datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00')).replace(tzinfo=None) for comment in item.comments + item.review_comments]
    all_dates = [created_at] + comment_dates
    if not any(rules['start_date'] <= date <= rules['end_date'] for date in all_dates):
        logger.info(f"Filtering out '{item.title}' because neither its creation time nor any comment time is within the date range.")
        return False

    # Rule 2: Comments containing tags of the specified user
    specified_user = rules.get('specified_user', '')
    # Lambda function to check if the specified user is not in the description
    _not_in_desc = lambda : specified_user not in item.description
    # Lambda function to check if the specified user is not in the comments
    _not_in_comments = lambda : not any(specified_user in comment['body'] for comment in item.comments)
    # Lambda function to check if the specified user is not in the reviewers
    _not_in_reviewers = lambda : specified_user not in item.reviewers

    if specified_user and _not_in_desc() and _not_in_comments() and _not_in_reviewers():
        logger.info(f"Filtering out '{item.title}' because it does not contain a comment tagging the user '{specified_user}'.")
        return False

    # Rule 3: Filter by the number of CCed users in the description
    if specified_user and not _not_in_desc():
        desc = item.description if item.description else ""
        if desc.count('@') > rules['number_of_ccer']:
            logger.info(f"Filtering out '{item.title}' because the description contains more than {rules['number_of_ccer']} CCed users.")
            return False

    # Rule 4: Ignore titles starting with "DISABLED"
    if item.title.startswith("DISABLED"):
        logger.info(f"Filtering out '{item.title}' because the title starts with 'DISABLED'.")
        return False

    # Rule 5: Ignore comments tagging or created by specific bots
    ignored_authors = {"pytorchmergebot", "pytorch-bot[bot]", "facebook-github-bot"}
    item.comments = [comment for comment in item.comments if comment['author'] not in ignored_authors]
    item.review_comments = [review_comment for review_comment in item.review_comments if review_comment['author'] not in ignored_authors]

    # Rule 5: Filter out items if all comments within the specified date range are created by ignored authors
    filtered_comments = [comment for comment in item.comments + item.review_comments if rules['start_date'] <= datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00')).replace(tzinfo=None) <= rules['end_date']]
    if filtered_comments and all(comment['author'] in ignored_authors for comment in filtered_comments):
        logger.info(f"Filtering out '{item.title}' because all comments within the specified date range are created by ignored authors.")
        return False

    return True

def print_items(items, dump_comments=False):
    """
    Print the filtered GitHub items to stdout.
    """
    for item in items:
        print(item.full_str(need_comments=dump_comments))
        print()

def main():
    parser = argparse.ArgumentParser(description="Fetch, filter, and display GitHub issues and pull requests for a specified repository.")
    parser.add_argument("--owner", type=str, default="pytorch", help="Owner of the GitHub repository")
    parser.add_argument("--repo", type=str, default="pytorch", help="Name of the GitHub repository")
    parser.add_argument("--start-date", type=str, default=datetime.utcnow().strftime("%Y-%m-%d"), help="Start date for fetching and filtering issues and PRs (YYYY-MM-DD format)")
    parser.add_argument("--end-date", type=str, default=datetime.utcnow().strftime("%Y-%m-%d"), help="End date for fetching and filtering issues and PRs (YYYY-MM-DD format)")
    parser.add_argument("--db-path", type=str, default=None, help="Path to the database folder")
    parser.add_argument("--specified-user", type=str, default="", help="User to look for in comments (default: no filtering)")
    parser.add_argument("--number-of-ccer", type=int, default=100, help="Number of CCERs in the comments")
    parser.add_argument("--log-level", type=str, default="WARNING", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--retrieve-only", action="store_true", help="Retrieve data only without filtering or dumping information")
    parser.add_argument("--dump-comments", action="store_true", help="Dump detailed comments and review comments for each item")
    parser.add_argument("--only-issues", action="store_true", help="Dump only issues (default: dump both issues and PRs)")
    parser.add_argument("--only-prs", action="store_true", help="Dump only pull requests (default: dump both issues and PRs)")
    parser.add_argument("--print-items", action="store_true", help="Print the filtered GitHub items to stdout")
    parser.add_argument("--no-summarize", action="store_true", help="Do not summarize the filtered GitHub items")
    parser.add_argument("--serving", type=str, choices=["OpenAI", "DeepSeek"], default="DeepSeek", help="Which serving to be called")
    parser.add_argument("--combine-summaries", action="store_true", help="Combine summaries")
    parser.add_argument("--send-email", action="store_true", help="Send email with the filtered items")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING), format='%(asctime)s - %(levelname)s - %(message)s')

    if not args.db_path:
        db_path = f"{args.owner}_{args.repo}_db"
    else:
        db_path = args.db_path

    token, _, _ = get_tokens()
    start_date = args.start_date + "T00:00:00Z"
    end_date = args.end_date + "T23:59:59Z"
    cur_date = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    # Parse start and end dates for filtering
    filter_start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)
    filter_end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)

    if not token:
        logger.error("Error: GitHub token not found in environment variables.")
    else:
        g = Github(token)
        repo = g.get_repo(f"{args.owner}/{args.repo}")

        with shelve.open(db_path) as db:
            logger.info("Starting to fetch issues and pull requests...")
            refresh_items(repo, start_date, end_date, db)
            refresh_item_comments(repo, start_date, db)

            # Load items from the database
            items = list(db.values())

        if not args.retrieve_only:
            # Define filtering rules
            rules = {
                'start_date': filter_start_date,
                'end_date': filter_end_date,
                'specified_user': args.specified_user,
                'number_of_ccer': args.number_of_ccer
            }

            # Apply PR or issue only filters
            if args.only_issues:
                items = [item for item in items if '/pull/' not in item.url]
            elif args.only_prs:
                items = [item for item in items if '/pull/' in item.url]

            # Filter items according to the rules
            filtered_items = filter_items(items, rules)

            if args.print_items:
                # Print filtered items
                logger.info("Filtered GitHub Items:")
                print_items(filtered_items, dump_comments=args.dump_comments)

            if not args.no_summarize:
                instruction = """
You are provided with a list of GitHub issues and pull requests (PRs), each detailed with specific information in the following format:

---
Title: [Issue or PR Title]
URL: [Issue or PR URL]
Description: [Detailed description]
Submitter: [Username of the person who submitted]
Tags: [Relevant tags]
Assignees: [Assigned users]
Reviewers: [Reviewers, if any]
Created At: [Creation date]
State: [Current state, e.g., open, closed]
Comments: [Number of comments]
Review Comments: [Number of review comments]
Commented by [Username] (created at [Date]): [Comment content]
...
---

Please generate a blog-style summary of the following list of GitHub issues and pull requests. The summary should:

- Be concise, be concise, be concise.

- Describe each issue or PR within two sentences.

- Mention the "URL" when referring to any issue or PR for easy reference.

- Logically group related issues and PRs to enhance readability. Describe the grouped issues and PRs together in a single paragraph.

- Make it more like an article instead of a laundary list. DO NOT make a list.

Below is an example excerpt FYI ("..." is used for brevity). Note that you don't have to strictly follow the structure
but it is the "blog-style" summary we are looking for:
```
In recent ... GitHub updates, several enhancements, fixes, and optimizations are being made across ...
The [PR #...](https://github.com/...)... introduces ... for ..., helping optimize ... Related to efficiency,
[PR #...](https://github.com/...) ... addresses ..., significantly speeding up data movement.

Enhancements in ... appear frequently. For example, the PR ... expands ... to better handle ...,
while [PR #...](https://github.com/...) improves ... mechanisms. Constant folding in lifted
graphs has been updated to support ..., as detailed in [PR #...](https://github.com/...).

In addition to these updates, ...

Finally, various infrastructure updates ...
```

Below is the detailed information for generating the summary:

    """
                summaries = text_summarize([item.full_str(need_comments=args.dump_comments) for item in filtered_items], serving=args.serving, instruction=instruction)
                if args.combine_summaries:
                    combine_instruction = """
Please combine the summaries of the individual GitHub issues and pull requests into a single blog-style summary.
Requirements:
 - You may rearrange the content according to their relevance and re-group them accordingly.
 - Please retain all the information of issues and PRs. DO NOT miss any. DO NOT miss any. DO NOT miss any.
 
Below are the concatenated summaries:

"""
                    summaries = text_summarize(summaries, instruction=combine_instruction)
                logger.info("Summary of filtered GitHub Items:")
                for summary in summaries:
                    print(summary)
                    print()

                cur_file_path = os.path.dirname(os.path.abspath(__file__))
                # Get current hour in 24H and add the info to the file name. Example,
                #  - current hour is 3 A.M, then the file name is "github_items_2022-01-01_2022-01-01_03.json"
                #  - current hour is 3 P.M, then the file name is "github_items_2022-01-01_2022-01-01_15.json"
                file_extension = "md"
                cur_file_name = f"summary_{args.owner}_{args.repo}_{cur_date}.{file_extension}"
                md_file_path = os.path.join(cur_file_path, cur_file_name)

                with open(md_file_path, 'w') as f:
                    filter_start_date = filter_start_date.strftime("%Y-%m-%d %H-%M-%S")
                    filter_end_date = filter_end_date.strftime("%Y-%m-%d %H-%M-%S")
                    f.write(f"Summary of {args.owner}/{args.repo} from {filter_start_date} to {filter_end_date}:\n\n")
                    for summary in summaries:
                        f.writelines(summary)

                if args.send_email:
                    send_email_with_attachment(
                        file_path=md_file_path,
                        subject=f"{args.owner}/{args.repo} - {cur_file_name}",
                        from_email=f"summarize_{args.owner}_{args.repo}@intel.com",
                        to_email="eikan.wang@intel.com,liangang.zhang@intel.com"
                    )

if __name__ == "__main__":
    main()
