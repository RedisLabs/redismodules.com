import logging
import os
from datetime import datetime

from github import Github
from rq_scheduler import Scheduler

from redisearchjson import Client, NumericField, Path, TextField

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def callUpateStats(docId):
    module = RedisModule(docId)
    module.updateStats()

class RedisModule(object):
    _conn = None
    docId = None

    def __init__(self, docId, mod=None, conn=None):
        if not conn:
            self._conn = Client(os.environ['REDIS_URL'], 'idx')
        else:
            self._conn = conn
        self.docId = docId

        if mod:
            # Store the module
            self._conn.jsonset(docId, Path.rootPath(), mod)
            # Index it
            self._conn.add_document(docId, nosave=True,
                name=mod['name'],
                description=mod['description'],
            )

            # Schedule a job to refresh repository statistics, starting from now and every 4 hours
            s = Scheduler(connection=self._conn)
            s.schedule(
                scheduled_time=datetime.utcnow(),
                func=callUpateStats,
                args=[docId],
                interval=60*60*4,
                repeat=None,
                ttl=0,
                result_ttl=0
            )

    def updateStats(self):
        # github.enable_console_debug_logging()
        gh = Github(os.environ['GITHUB_TOKEN'])
        repo = self._conn.jsonget(self.docId, Path('.repository'))

        if repo and \
            'type' in repo and repo['type'] == 'github' and \
            'name' in repo:

            logger.info('Fetching stats for {}...'.format(repo['name']))
            g = gh.get_repo(repo['name'])
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
        self._conn.add_document(self.docId, nosave=True, replace=True, **stats)
