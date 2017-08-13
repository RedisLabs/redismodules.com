import logging
import os
import re
from datetime import datetime

from github import Github

from redisearchjson import Client, NumericField, Path, TextField, Suggestion
from stopwords import stopwords

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def callUpateStats(db_url, docId, ghlogin_or_token, index='ix', ac='ac'):
    conn = Client(db_url, index, ac)
    module = RedisModule(conn, docId)
    module.updateStats(ghlogin_or_token)

class RedisModule(object):
    _conn = None
    docId = None

    def __init__(self, conn, docId):
        self._conn = conn
        self.docId = docId

    def load(self, mod):
        # Store the module
        self._conn.jsonset(self.docId, Path.rootPath(), mod)
        # Index it
        self._conn.add_document(self.docId, nosave=True,
            name=mod['name'],
            description=mod['description'], 
        )
        # Add the module's name and description to the suggestions engine
        text = '{} {}'.format(mod['name'], mod['description'])
        words = set(re.compile('\w+').findall(text))
        words = set(w.lower() for w in words)
        words = words.difference(stopwords)
        self._conn.add_suggestions(*[Suggestion(w) for w in words])

    def updateStats(self, ghlogin_or_token):
        # github.enable_console_debug_logging()
        gh = Github(ghlogin_or_token)
        mod = self._conn.jsonget(self.docId, Path('name'), Path('description'), Path('repository'))
        repo = mod['repository']

        if repo and \
            'type' in repo and repo['type'] == 'github' and \
            'id' in repo:

            logger.info('Fetching stats for {}...'.format(repo['id']))
            g = gh.get_repo(repo['id'])
            stats = {
                'stargazers_count': g.stargazers_count,
                'forks_count': g.forks_count,
                'last_modified': (datetime.today() - g.pushed_at).days  # TODO: take last push from default branch
            }

            rel = g.get_releases()
            try:
                stats['last_release'] = {
                    'name': rel[0].tag_name,
                    'url': rel[0].url
                }
            except IndexError:
                pass

        self._conn.jsonset(self.docId, Path('.stats'), stats)
        self._conn.add_document(self.docId, nosave=True, replace=True, name=mod['name'], description=mod['description'], **stats)
