#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021-2022 Willem Jiang, Yehu Wang, Chenqi Shan, Fugang Xiao
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     Willem Jiang <willem.jiang@gmail.com>
#     Yehu Wang <yehui.wang.mdh@gmail.com>
#     Chenqi Shan <chenqishan337@gmail.com>
#     Fugang Xiao <xiao623@outlook.com>

import json
import logging

import requests
from grimoirelab_toolkit.datetime import (datetime_to_utc,
                                          str_to_datetime, datetime_utcnow)
from grimoirelab_toolkit.uris import urijoin

from ...backend import (Backend,
                              BackendCommand,
                              BackendCommandArgumentParser,
                              DEFAULT_SEARCH_FIELD)
from ...client import HttpClient, RateLimitHandler
from ...utils import DEFAULT_DATETIME, DEFAULT_LAST_DATETIME

CATEGORY_ISSUE = "issue"
CATEGORY_PULL_REQUEST = "pull_request"
CATEGORY_REPO = 'repository'

GITEE_URL = "https://gitee.com/"
GITEE_API_URL = "https://gitee.com/api/v5"
GITEE_REFRESH_TOKEN_URL = "https://gitee.com/oauth/token"

# Range before sleeping until rate limit reset
MIN_RATE_LIMIT = 10
MAX_RATE_LIMIT = 500

# Use this factor of the current token's remaining API points before switching to the next token
TOKEN_USAGE_BEFORE_SWITCH = 0.1

MAX_CATEGORY_ITEMS_PER_PAGE = 100
PER_PAGE = 100

# Default sleep time and retries to deal with connection/server problems
DEFAULT_SLEEP_TIME = 1
MAX_RETRIES = 5

TARGET_ISSUE_FIELDS = ['user', 'assignee', 'collaborators', 'comments']
TARGET_PULL_FIELDS = ['user', 'assignees', 'number', "assignees", "testers"]
# 'review_comments', 'requested_reviewers',  "merged_by", "commits"

logger = logging.getLogger(__name__)


class Gitee(Backend):
    """Gitee backend for Perceval.

    This class allows the fetch the issues stored in Gitee repostory.
    ```
    Gitee(
        owner='chaoss', repository='grimoirelab-perceval-gitee',
        api_token=[TOKEN-1], sleep_for_rate=True,
        sleep_time=300
    )
    ```

    :param owner: Gitee owner
    :param repository: Gitee repository from the owner
    :param api_token: list of Gitee auth tokens to access the API
    :param base_url: Gitee URL in enterprise edition case;
        when no value is set the backend will be fetch the data
        from the Gitee public site.
    :param tag: label used to mark the data
    :param archive: archive to store/retrieve items
    :param sleep_for_rate: sleep until rate limit is reset
    :param min_rate_to_sleep: minimum rate needed to sleep until
         it will be reset
    :param max_retries: number of max retries to a data source
        before raising a RetryError exception
    :param max_items: max number of category items (e.g., issues,
        pull requests) per query
    :param sleep_time: time to sleep in case
        of connection problems
    :param ssl_verify: enable/disable SSL verification
    """
    version = '0.1.0'

    CATEGORIES = [CATEGORY_ISSUE, CATEGORY_PULL_REQUEST, CATEGORY_REPO]

    CLASSIFIED_FIELDS = [
        ['user_data'],
        ['merged_by_data'],
        ['assignee_data'],
        ['assignees_data'],
        ['requested_reviewers_data'],
        ['comments_data', 'user_data'],
        ['reviews_data', 'user_data'],
        ['review_comments_data', 'user_data']
    ]

    def __init__(self, owner=None, repository=None,
                 api_token=None, base_url=None,
                 tag=None, archive=None,
                 sleep_for_rate=False, min_rate_to_sleep=MIN_RATE_LIMIT,
                 max_retries=MAX_RETRIES, sleep_time=DEFAULT_SLEEP_TIME,
                 max_items=MAX_CATEGORY_ITEMS_PER_PAGE, ssl_verify=True):
        if api_token is None:
            api_token = []
        origin = base_url if base_url else GITEE_URL
        origin = urijoin(origin, owner, repository)

        super().__init__(origin, tag=tag, archive=archive, ssl_verify=ssl_verify)

        self.owner = owner
        self.repository = repository
        self.api_token = api_token
        self.base_url = base_url

        self.sleep_for_rate = sleep_for_rate
        self.min_rate_to_sleep = min_rate_to_sleep
        self.max_retries = max_retries
        self.sleep_time = sleep_time
        self.max_items = max_items

        self.client = None
        self.exclude_user_data = False
        self._users = {}  # internal users cache

    def search_fields(self, item):
        """Add search fields to an item.

        It adds the values of `metadata_id` plus the `owner` and `repo`.

        :param item: the item to extract the search fields values

        :returns: a dict of search fields
        """
        search_fields = {
            DEFAULT_SEARCH_FIELD: self.metadata_id(item),
            'owner': self.owner,
            'repo': self.repository
        }

        return search_fields

    def fetch(self, category=CATEGORY_ISSUE, from_date=DEFAULT_DATETIME, to_date=DEFAULT_LAST_DATETIME,
              filter_classified=False):
        """Fetch the issues/pull requests from the repository.

        The method retrieves, from a Gitee repository, the issues/pull requests
        updated since the given date.

        :param category: the category of items to fetch
        :param from_date: obtain issues/pull requests updated since this date
        :param to_date: obtain issues/pull requests until a specific date (included)
        :param filter_classified: remove classified fields from the resulting items

        :returns: a generator of issues
        """
        self.exclude_user_data = filter_classified

        if self.exclude_user_data:
            logger.info("Excluding user data. Personal user information won't be collected from the API.")

        if not from_date:
            from_date = DEFAULT_DATETIME
        if not to_date:
            to_date = DEFAULT_LAST_DATETIME

        from_date = datetime_to_utc(from_date)
        to_date = datetime_to_utc(to_date)

        kwargs = {
            'from_date': from_date,
            'to_date': to_date
        }
        items = super().fetch(category,
                              filter_classified=filter_classified,
                              **kwargs)

        return items

    def fetch_items(self, category, **kwargs):
        """Fetch the items (issues or pull_requests or repo information)

        :param category: the category of items to fetch
        :param kwargs: backend arguments

        :returns: a generator of items
        """
        from_date = kwargs['from_date']
        to_date = kwargs['to_date']

        if category == CATEGORY_ISSUE:
            items = self.__fetch_issues(from_date, to_date)
        elif category == CATEGORY_PULL_REQUEST:
            items = self.__fetch_pull_requests(from_date, to_date)
        else:
            items = self.__fetch_repo_info()

        return items

    @classmethod
    def has_archiving(cls):
        """Returns whether it supports archiving items on the fetch process.

        :returns: this backend supports items archive
        """
        return True

    @classmethod
    def has_resuming(cls):
        """Returns whether it supports to resume the fetch process.

        :returns: this backend supports items resuming
        """
        return True

    @staticmethod
    def metadata_id(item):
        """Extracts the identifier from a Gitee item."""

        if "forks_count" in item:
            return str(item['fetched_on'])
        else:
            return str(item['id'])

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a Gitee item.

        The timestamp used is extracted from 'updated_at' field.
        This date is converted to UNIX timestamp format. As Gitee
        dates are in UTC the conversion is straightforward.

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """
        if "forks_count" in item:
            return item['fetched_on']
        else:
            ts = item['updated_at']
            ts = str_to_datetime(ts)

            return ts.timestamp()

    @staticmethod
    def metadata_category(item):
        """Extracts the category from a Gitee item.

        This backend generates three types of item which are
        'issue', 'pull_request' and 'repo' information.
        """

        if "base" in item:
            category = CATEGORY_PULL_REQUEST
        elif "forks_count" in item:
            category = CATEGORY_REPO
        else:
            category = CATEGORY_ISSUE

        return category

    def _init_client(self, from_archive=False):
        """Init client"""

        return GiteeClient(self.owner, self.repository, self.api_token, self.base_url,
                           self.sleep_for_rate, self.min_rate_to_sleep,
                           self.sleep_time, self.max_retries, self.max_items,
                           self.archive, from_archive, self.ssl_verify)

    def __fetch_issues(self, from_date, to_date):
        """Fetch the issues"""

        issues_groups = self.client.issues(from_date=from_date)

        for raw_issues in issues_groups:
            issues = json.loads(raw_issues)
            for issue in issues:

                if str_to_datetime(issue['updated_at']) > to_date:
                    return

                self.__init_extra_issue_fields(issue)
                for field in TARGET_ISSUE_FIELDS:
                    if not issue[field]:
                        continue
                    if field == 'user':
                        issue[field + '_data'] = self.__get_user(issue[field]['login'])
                    elif field == 'assignee':
                        issue[field + '_data'] = self.__get_issue_assignee(issue[field])
                    elif field == 'collaborators':
                        issue[field + '_data'] = self.__get_issue_collaborators(issue[field])
                    elif field == 'comments':
                        issue[field + '_data'] = self.__get_issue_comments(issue['number'])
                yield issue

    def __fetch_pull_requests(self, from_date, to_date):
        """Fetch the pull requests"""

        raw_pulls_groups = self.client.pulls(from_date=from_date)
        for raw_pulls in raw_pulls_groups:
            pulls = json.loads(raw_pulls)
            for pull in pulls:
                if str_to_datetime(pull['updated_at']) < from_date \
                        or str_to_datetime(pull['updated_at']) > to_date:
                    return

                self.__init_extra_pull_fields(pull)

                for field in TARGET_PULL_FIELDS:
                    if not pull[field]:
                        continue

                    if field == 'user':
                        pull[field + '_data'] = self.__get_user(pull[field]['login'])

                    elif field == 'merged_by':
                        pull[field + '_data'] = self.__get_user(pull[field]['login'])

                    elif field == 'assignees' or field == 'testers':
                        pull[field + '_data'] = self.__get_users(pull[field])
                    elif field == 'number':
                        pull['review_comments_data'] = self.__get_pull_review_comments(pull['number'])
                        pull['commits_data'] = self.__get_pull_commits(pull['number'])
                        pull['merged_by'] = self.__get_pull_merged_by(pull['number'])
                        if pull['merged_by']:
                            pull['merged_by_data'] = self.__get_user(pull['merged_by'])
                yield pull

    def __fetch_repo_info(self):
        """Get repo info about stars, watchers and forks"""

        raw_repo = self.client.repo()
        repo = json.loads(raw_repo)

        raw_repo_releases = self.client.repo_releases()
        repo_releases = json.loads(raw_repo_releases)
        repo['releases'] = repo_releases

        fetched_on = datetime_utcnow()
        repo['fetched_on'] = fetched_on.timestamp()

        yield repo

    def __get_issue_comments(self, issue_number):
        """Get issue comments"""

        comments = []
        group_comments = self.client.issue_comments(issue_number)

        for raw_comments in group_comments:

            for comment in json.loads(raw_comments):
                comment_id = comment.get('id')
                comment['user_data'] = self.__get_user(comment['user']['login'])
                comments.append(comment)

        return comments

    def __get_issue_collaborators(self, raw_collaborators):
        """Get issue collaborators"""

        collaborators = []
        for ra in raw_collaborators:
            collaborators.append(self.__get_user(ra['login']))

        return collaborators

    def __get_pull_merged_by(self, pr_number):
        group_raw_action_logs = self.client.pull_action_logs(pr_number)
        result = None
        for raw_action_logs in group_raw_action_logs:
            action_logs = json.loads(raw_action_logs)
            for action_log in action_logs:
                if action_log["action_type"] == "merged_pr":
                    result = action_log["user"]["login"]
                    break
        return result

    def __get_pull_commits(self, pr_number):
        """Get pull request commit hashes"""

        hashes = []
        try:
            group_pull_commits = self.client.pull_commits(pr_number)

            for raw_pull_commits in group_pull_commits:

                for commit in json.loads(raw_pull_commits):
                    commit_hash = commit['sha']
                    hashes.append(commit_hash)

        except requests.exceptions.HTTPError as error:
            # 404 not found is wrongly received from gitee API service
            if error.response.status_code == 404:
                logger.error("Can't get gitee pull request commits with PR number %s", pr_number)
            else:
                raise error
        return hashes

    def __get_pull_review_comments(self, pr_number):
        """Get pull request review comments"""

        comments = []
        try:
            group_comments = self.client.pull_review_comments(pr_number)
            for raw_comments in group_comments:

                for comment in json.loads(raw_comments):
                    comment_id = comment.get('id')

                    user = comment.get('user', None)
                    if not user:
                        logger.warning("Missing user info for %s", comment['url'])
                        comment['user_data'] = None
                    else:
                        comment['user_data'] = self.__get_user(user['login'])
                    comments.append(comment)
        except requests.exceptions.HTTPError as error:
            # 404 not found is wrongly received from gitee API service
            if error.response.status_code == 404:
                logger.error("Can't get gitee pull request comments with PR number %s", pr_number)
            else:
                raise error

        return comments

    # TODO need to check the Gitee API for the pull reviews
    def __get_pull_reviews(self, pr_number):
        """Get pull request reviews"""
        reviews = []
        group_reviews = self.client.pull_reviews(pr_number)

        for raw_reviews in group_reviews:

            for review in json.loads(raw_reviews):
                user = review.get('user', None)
                if not user:
                    logger.warning("Missing user info for %s", review['html_url'])
                    review['user_data'] = None
                else:
                    review['user_data'] = self.__get_user(user['login'])

                reviews.append(review)

        return reviews

    def __get_users(self, items):
        users = []
        for item in items:
            user = self.__get_user(item['login'])
            users.append(user)
        return users

    def __get_user(self, login):
        """Get user and org data for the login"""

        if not login or self.exclude_user_data:
            return None

        user_raw = self.client.user(login)
        user = json.loads(user_raw)
        user_orgs_raw = \
            self.client.user_orgs(login)
        user['organizations'] = json.loads(user_orgs_raw)

        return user

    def __get_issue_assignee(self, raw_assignee):
        """Get issue assignee"""
        assignee = self.__get_user(raw_assignee['login'])

        return assignee

    def __init_extra_issue_fields(self, issue):
        """Add fields to an issue"""

        issue['user_data'] = {}
        issue['assignee_data'] = {}
        issue['assignees_data'] = []
        issue['comments_data'] = []

    def __init_extra_pull_fields(self, pull):
        """Add fields to a pull request"""

        pull['user_data'] = {}
        pull['review_comments_data'] = {}
        pull['reviews_data'] = []
        pull['merged_by_data'] = []
        pull['commits_data'] = []


class GiteeClient(HttpClient, RateLimitHandler):
    """Client for retrieving information from Gitee API

    :param owner: Gitee owner
    :param repository: Gitee repository from the owner
    :param tokens: list of Gitee auth tokens to access the API
    :param base_url: Gitee URL in enterprise edition case;
        when no value is set the backend will be fetch the data
        from the Gitee public site.
    :param sleep_for_rate: sleep until rate limit is reset
    :param min_rate_to_sleep: minimun rate needed to sleep until
         it will be reset
    :param sleep_time: time to sleep in case
        of connection problems
    :param max_retries: number of max retries to a data source
        before raising a RetryError exception
    :param max_items: max number of category items (e.g., issues,
        pull requests) per query
    :param archive: collect issues already retrieved from an archive
    :param from_archive: it tells whether to write/read the archive
    :param ssl_verify: enable/disable SSL verification
    """
    EXTRA_STATUS_FORCELIST = [403, 500, 502, 503]

    _users = {}  # users cache
    _users_orgs = {}  # users orgs cache

    def __init__(self, owner, repository, tokens,
                 base_url=None, sleep_for_rate=False, min_rate_to_sleep=MIN_RATE_LIMIT,
                 sleep_time=DEFAULT_SLEEP_TIME, max_retries=MAX_RETRIES,
                 max_items=MAX_CATEGORY_ITEMS_PER_PAGE, archive=None, from_archive=False, ssl_verify=True):
        self.owner = owner
        self.repository = repository
        # Just take the first token from tokens
        if tokens:
            self.access_token = tokens[0]
        else:
            self.access_token = None
        # Gitee doesn't have rate limit check yet
        self.last_rate_limit_checked = None
        self.max_items = max_items

        if base_url:
            base_url = urijoin(base_url, 'api', 'v5')
        else:
            base_url = GITEE_API_URL

        super().__init__(base_url, sleep_time=sleep_time, max_retries=max_retries,
                         extra_headers=self._set_extra_headers(),
                         extra_status_forcelist=self.EXTRA_STATUS_FORCELIST,
                         archive=archive, from_archive=from_archive, ssl_verify=ssl_verify)
        # refresh the access token
        self._refresh_access_token()

    def issue_comments(self, issue_number):
        """Get the issue comments """

        payload = {
            'per_page': PER_PAGE
            # we don't set the since option here
        }

        path = urijoin("issues", issue_number, "comments")
        return self.fetch_items(path, payload)

    def issues(self, from_date=None):
        """Fetch the issues from the repository.

        The method retrieves, from a Gitee repository, the issues
        updated since the given date.

        :param from_date: obtain issues updated since this date

        :returns: a generator of issues
        """
        payload = {
            'state': 'all',
            'per_page': self.max_items,
            'direction': 'asc',
            'sort': 'updated'
        }

        if from_date:
            payload['since'] = from_date.isoformat()

        path = urijoin("issues")
        return self.fetch_items(path, payload)

    def pulls(self, from_date=None):
        """Fetch the pull requests from the repository.

        The method retrieves, from a Gitee repository, the pull requests
        updated since the given date.

        :param from_date: obtain pull requests updated since this date

        :returns: a generator of pull requests
        """
        payload = {
            'state': 'all',
            'per_page': 100,
            'direction': 'asc',
            'sort': 'updated'
        }
        
        if from_date:
            payload['since'] = from_date.isoformat()

        path = urijoin("pulls")
        return self.fetch_items(path, payload)

    def repo(self):
        """Get repository data"""

        path = urijoin(self.base_url, 'repos', self.owner, self.repository)
    
        r = self.fetch(path)
        repo = r.text

        return repo

    def repo_releases(self):
        """Get repository releases data"""

        path = urijoin(self.base_url, 'repos', self.owner, self.repository,'releases?page=1&per_page=100')
    
        r = self.fetch(path)
        repo_releases = r.text

        return repo_releases  

    def pull_action_logs(self, pr_number):
        """Get pull request action logs"""

        pull_action_logs_path = urijoin("pulls", str(pr_number), "operate_logs")
        return self.fetch_items(pull_action_logs_path, {})

    def pull_commits(self, pr_number):
        """Get pull request commits"""

        payload = {
            'per_page': PER_PAGE,
        }

        commit_url = urijoin("pulls", str(pr_number), "commits")
        return self.fetch_items(commit_url, payload)

    def pull_review_comments(self, pr_number):
        """Get pull request review comments"""

        payload = {
            'per_page': PER_PAGE,
            'direction': 'asc',
            # doesn't support sort parameter
            # 'sort': 'updated'
        }

        comments_url = urijoin("pulls", str(pr_number), "comments")
        return self.fetch_items(comments_url, payload)

    def user(self, login):
        """Get the user information and update the user cache"""
        user = None

        if login in self._users:
            return self._users[login]

        url_user = urijoin(self.base_url, 'users', login)

        logger.debug("Getting info for %s" % url_user)

        r = self.fetch(url_user)
        user = r.text
        self._users[login] = user

        return user

    def user_orgs(self, login):
        """Get the user public organizations"""
        if login in self._users_orgs:
            return self._users_orgs[login]

        url = urijoin(self.base_url, 'users', login, 'orgs')
        try:
            r = self.fetch(url)
            orgs = r.text
        except requests.exceptions.HTTPError as error:
            # 404 not found is wrongly received sometimes
            if error.response.status_code == 404:
                logger.error("Can't get gitee login orgs with %s", url)
                orgs = '[]'
            else:
                raise error

        self._users_orgs[login] = orgs

        return orgs

    def fetch(self, url, payload=None, headers=None, method=HttpClient.GET, stream=False, auth=None):
        """Fetch the data from a given URL.

        :param url: link to the resource
        :param payload: payload of the request
        :param headers: headers of the request
        :param method: type of request call (GET or POST)
        :param stream: defer downloading the response body until the response content is available
        :param auth: auth of the request

        :returns a response object
        """
        # Add the access_token to the payload
        if self.access_token:
            if not payload:
                payload = {}
            payload["access_token"] = self.access_token

        response = super().fetch(url, payload, headers, method, stream, auth)

        # if not self.from_archive:
        #    if self._need_check_tokens():
        #        self._choose_best_api_token()
        #    else:
        #        self.update_rate_limit(response)

        return response

    def fetch_items(self, path, payload):
        """Return the items from gitee API using links pagination"""

        page = 0  # current page
        total_page = None  # total page number
        url_next = urijoin(self.base_url, 'repos', self.owner, self.repository, path)
        logger.debug("Get Gitee paginated items from " + url_next)

        response = self.fetch(url_next, payload=payload)

        items = response.text
        page += 1

        total_page = response.headers.get('total_page')
        if total_page:
            total_page = int(total_page[0])
            logger.debug("Page: %i/%i" % (page, total_page))

        while items:
            yield items
            items = None
            if 'next' in response.links:
                url_next = response.links['next']['url']
                response = self.fetch(url_next, payload=payload)
                page += 1
                items = response.text
                logger.debug("Page: %i/%i" % (page, total_page))

    def _set_extra_headers(self):
        """Set extra headers for session"""
        headers = {}
        # set the header for request
        headers.update({'Content-Type': 'application/json;charset=UTF-8'})
        return headers

    def _refresh_access_token(self):
        """Send a refresh post access to the Gitee Server"""
        if self.access_token:
            url = GITEE_REFRESH_TOKEN_URL + "?grant_type=refresh_token&refresh_token=" + self.access_token
            logger.info("Refresh the access_token for Gitee API")
            self.session.post(url, data=None, headers=None, stream=False, verify=self.ssl_verify, auth=None)


class GiteeCommand(BackendCommand):
    """Class to run Gitee backend from the command line."""

    BACKEND = Gitee

    @classmethod
    def setup_cmd_parser(cls):
        """Returns the Gitee argument parser."""

        parser = BackendCommandArgumentParser(cls.BACKEND,
                                              from_date=True,
                                              to_date=True,
                                              token_auth=False,
                                              archive=True,
                                              ssl_verify=True)
        # Gitee options
        group = parser.parser.add_argument_group('Gitee arguments')
        group.add_argument('--sleep-for-rate', dest='sleep_for_rate',
                           action='store_true',
                           help="sleep for getting more rate")
        group.add_argument('--min-rate-to-sleep', dest='min_rate_to_sleep',
                           default=MIN_RATE_LIMIT, type=int,
                           help="sleep until reset when the rate limit reaches this value")
        # Gitee token(s)
        group.add_argument('-t', '--api-token', dest='api_token',
                           nargs='+',
                           default=[],
                           help="list of Gitee API tokens")

        # Generic client options
        group.add_argument('--max-items', dest='max_items',
                           default=MAX_CATEGORY_ITEMS_PER_PAGE, type=int,
                           help="Max number of category items per query.")
        group.add_argument('--max-retries', dest='max_retries',
                           default=MAX_RETRIES, type=int,
                           help="number of API call retries")
        group.add_argument('--sleep-time', dest='sleep_time',
                           default=DEFAULT_SLEEP_TIME, type=int,
                           help="sleeping time between API call retries")

        # Positional arguments
        parser.parser.add_argument('owner',
                                   help="Gitee owner")
        parser.parser.add_argument('repository',
                                   help="Gitee repository")

        return parser
