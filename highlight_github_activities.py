from dataclasses import dataclass
import sys
from github import Github
from datetime import datetime, timedelta
import os
import argparse
import logging
from dotenv import load_dotenv
import json

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from mail_util import send_email_with_attachment

load_dotenv()

logger = logging.getLogger(__name__)

ignored_authors = {"pytorchmergebot", "pytorch-bot[bot]", "facebook-github-bot"}

@dataclass
class GithubLabel:
    name: str


class GitHubItem:
    def __init__(self, number, title, url, description, submitter, tags, assignees, reviewers, created_at, comments, review_comments, state):
        self.number = number
        self.title = title
        self.url = url
        self.html_url = url # To present github url
        self.description = description
        self.body = description
        self.submitter = submitter
        self.tags = tags
        self.labels = [GithubLabel(tag) for tag in tags] # To present github label
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

    def serialize(self):
        canomicalized_labels = [{"name": label} for label in self.tags]
        return {
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "body": self.description,
            "submitter": self.submitter,
            "labels": canomicalized_labels,
            "assignees": self.assignees,
            "reviewers": self.reviewers,
            "created_at": self.created_at,
            "comments": self.comments,
            "review_comments": self.review_comments,
            "state": self.state
        }

# Inquire GitHub activities
def inquire_github_activities(repo, start_date, end_date, interval, rules):
    start_date_dt = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ")
    end_date_dt = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ")

    all_issues = repo.get_issues(state='all', since=start_date_dt)

    github_items = []
    for item in all_issues:
        # If interval is NOT set, stop early if the item is outside of the date range
        if item.created_at.replace(tzinfo=None) > end_date_dt and interval == 0:
            logger.info("Reached items outside of date range. Stopping early.")
            break

        github_item = GitHubItem(
            item.number,
            item.title,
            item.html_url,
            item.body if item.body else "No description available",
            item.user.login if item.user else "Unknown",
            [label.name for label in item.labels],
            [assignee.login for assignee in item.assignees],
            [],
            item.created_at.isoformat(),
            [],
            [],
            item.state
        )
        github_item.reviewers = []
        # commented out for efficiency
        if '/pull/' in item.html_url:  # To distinguish pull requests by URL pattern
            pr = repo.get_pull(item.number)
            github_item.reviewers = list(set([review.user.login for review in pr.get_reviews() if review.user]))

            for review_comment in pr.get_review_comments():
                github_item.review_comments.append({
                    "author": review_comment.user.login,
                    "body": review_comment.body,
                    "created_at": review_comment.created_at.isoformat()
                })
        
        # Get comments for issues and pull requests
        for comment in item.get_comments():
            github_item.comments.append({
                "author": comment.user.login,
                "body": comment.body,
                "created_at": comment.created_at.isoformat()
            })

        if apply_rules(github_item, interval, rules):
            github_items.append(github_item.serialize())

    return github_items

def apply_rules(item: GitHubItem, interval, rules):
    """
    Check if a GitHub item satisfies the given filtering rules.
    """
    # Filter by start and end dates
    created_at = datetime.fromisoformat(item.created_at.replace('Z', '+00:00')).replace(tzinfo=None)
    comment_dates = [datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00')).replace(tzinfo=None) for comment in item.comments + item.review_comments]
    all_dates = [created_at] + comment_dates

    # If interval is set, filter out items outside of the date range
    if interval > 0:
        if not any(rules['start_date'] <= date for date in all_dates):
            logger.info(f"Filtering out '{item.title}' because it is outside of the date range.")
            return False
    else:
        if not any(rules['start_date'] <= date <= rules['end_date'] for date in all_dates):
            logger.info(f"Filtering out '{item.title}' because neither its creation time nor any comment time is within the date range.")
            return False

    # Comments containing tags of the specified user
    specified_user = rules.get('specified_user', 'EikanWang')
    # Lambda function to check if the specified user is not in the description
    _not_in_desc = lambda : specified_user not in item.description
    # Lambda function to check if the specified user is not in the comments
    _not_in_comments = lambda : not any(specified_user in comment['body'] for comment in item.comments)
    # Lambda function to check if the specified user is not in the reviewers
    _not_in_reviewers = lambda : specified_user not in item.reviewers
    # Lambda function to check if the item tags contains "xpu" literal while the tags is a string array and each item may contains "xpu"
    _xpu_label = lambda : any("xpu" in tag for tag in item.tags)

    # The title contains XPU
    if "xpu" in item.title.lower():
        logger.info(f"Filtering out '{item.title}' because it contains 'XPU'.")
        return True

    if _xpu_label():
        logger.info(f"Filtering out '{item.title}' because it is labeled with XPU.")
        return True

    if _not_in_desc() and _not_in_comments() and _not_in_reviewers():
        logger.info(f"Filtering out '{item.title}' because it does not contain a comment tagging the user '{specified_user}'.")
        return False

    # Filter by the number of CCed users in the description
    if not _not_in_desc():
        desc = item.description if item.description else ""
        if desc.count('@') > rules['number_of_ccer']:
            logger.info(f"Filtering out '{item.title}' because the description contains more than {rules['number_of_ccer']} CCed users.")
            return False

    # Ignore titles starting with "DISABLED"
    if item.title.startswith("DISABLED"):
        logger.info(f"Filtering out '{item.title}' because the title starts with 'DISABLED'.")
        return False

    # Ignore comments tagging or created by specific bots
    item.comments = [comment for comment in item.comments if comment['author'] not in ignored_authors]
    item.review_comments = [review_comment for review_comment in item.review_comments if review_comment['author'] not in ignored_authors]

    # Filter out items if all comments within the specified date range are created by ignored authors
    filtered_comments = [comment for comment in item.comments + item.review_comments if rules['start_date'] <= datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00')).replace(tzinfo=None) <= rules['end_date']]
    if filtered_comments and all(comment['author'] in ignored_authors for comment in filtered_comments):
        logger.info(f"Filtering out '{item.title}' because all comments within the specified date range are created by ignored authors.")
        return False

    return True

def main():
    parser = argparse.ArgumentParser(description="Fetch, filter, and display GitHub issues and pull requests for a specified repository.")
    parser.add_argument("--owner", type=str, default="pytorch", help="Owner of the GitHub repository")
    parser.add_argument("--repo", type=str, default="pytorch", help="Name of the GitHub repository")
    parser.add_argument("--start-date", type=str, default=datetime.utcnow().strftime("%Y-%m-%d"), help="Start date for fetching and filtering issues and PRs (YYYY-MM-DD format)")
    parser.add_argument("--end-date", type=str, default=datetime.utcnow().strftime("%Y-%m-%d"), help="End date for fetching and filtering issues and PRs (YYYY-MM-DD format)")
    parser.add_argument("--number-of-ccer", type=int, default=10, help="Number of CCERs in the comments")
    parser.add_argument("--interval", type=int, default=0, help="Intervel in hours to fetch the data")
    parser.add_argument("--only-issues", action="store_true", help="Dump only issues (default: dump both issues and PRs)")
    parser.add_argument("--send-email", action="store_true", help="Send email with the filtered items")
    parser.add_argument("--only-prs", action="store_true", help="Dump only pull requests (default: dump both issues and PRs)")
    parser.add_argument("--log-level", type=str, default="WARNING", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING), format='%(asctime)s - %(levelname)s - %(message)s')


    token = os.getenv("GITHUB_TOKEN")

    # Get current date and time
    now = datetime.now()
    cur_date_file_name = now.strftime('%Y-%m-%d_%H-%M-%S')

    if args.interval > 0:
        # Get the current date and time in the format of "YYYY-MM-DDTHH:MM:SSZ"
        current_date_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Get the start date by subtracting the interval from the current date and time
        start_date = now - timedelta(hours=args.interval)
        start_date = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Get the end date by adding the interval to the current date and time
        end_date = current_date_time
    else:
        start_date = args.start_date + "T00:00:00Z"
        end_date = args.end_date + "T23:59:59Z"

    # Parse start and end dates for filtering
    filter_start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)
    filter_end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=None)

    if not token:
        logger.error("Error: GitHub token not found in environment variables.")
    else:
        g = Github(token)
        repo = g.get_repo(f"{args.owner}/{args.repo}")

        logger.info("Starting to fetch issues and pull requests...")

        # Define filtering rules
        rules = {
            'start_date': filter_start_date,
            'end_date': filter_end_date,
            'number_of_ccer': args.number_of_ccer
        }
        github_items = inquire_github_activities(repo, start_date, end_date, args.interval, rules)

        # Serialize all the github_items to a well-formatted and pretty-printed JSON string
        # and save the JSON string to a file with full path and the file name is
        # "github_items" + start_date + "_" + end_date + ".json"
        # The json file should be saved in the same directory of this python file with full path
        cur_file_path = os.path.dirname(os.path.abspath(__file__))
        # Get current hour in 24H and add the info to the file name. Example,
        #  - current hour is 3 A.M, then the file name is "github_items_2022-01-01_2022-01-01_03.json"
        # -  current hour is 3 P.M, then the file name is "github_items_2022-01-01_2022-01-01_15.json"
        # -  current hour is 0 A.M, then the file name is "github_items_2022-01-01_2022-01-01_00.json"
        file_extension = "json"
        cur_file_name = f"highlight_{cur_date_file_name}.{file_extension}"
        json_file_path = os.path.join(cur_file_path, cur_file_name)

        filter_start_date = filter_start_date.strftime("%Y-%m-%d_%H:%M:%S")
        filter_end_date = filter_end_date.strftime("%Y-%m-%d_%H:%M:%S")

        with open(json_file_path, 'w') as f:
            github_items = [{"File Information": f"Highlights of {args.owner}/{args.repo} from {filter_start_date} to {filter_end_date}"}] + github_items
            json.dump(github_items, f, indent=4)

        if args.send_email:
            send_email_with_attachment(
                file_path=json_file_path,
                subject=f"{args.owner}/{args.repo} - {cur_file_name}",
                from_email=f"highlight_{args.owner}_{args.repo}@intel.com",
                to_email="eikan.wang@intel.com"
            )

if __name__ == "__main__":
    main()
