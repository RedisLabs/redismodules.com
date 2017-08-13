import hashlib
import json
import logging
import os
from datetime import datetime

from redis import StrictRedis
from rq_scheduler import Scheduler

from redisearchjson import Client, NumericField, Path, TextField, Query, SortbyField
from redismodule import RedisModule, callUpateStats
from stopwords import stopwords

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class Hub(object):

    _conn = None
    _key = 'hub:catalog'
    _directory = 'modules'

    def __init__(self, db_url, queue_url, ghlogin_or_token):
        logger.info('Initializing modules catalog')
        timestamp = datetime.utcnow()

        self._conn = Client(db_url, 'ix', 'ac')

        # Check if catalog exists
        if self._conn.exists(self._key):
            pass
        else:   # Create the catalog
            logger.info('Building catalog in Redis')

            # Store the master catalog as an object
            self._conn.jsonset(self._key, Path.rootPath(),
            {
                'created': timestamp.isoformat(),
                'modules': {},
            })

            # Create an index for the modules
            self._conn.create_index((
                TextField('name'),
                TextField('description'),
                NumericField('stargazers_count', sortable=True),
                NumericField('forks_count', sortable=True),
                NumericField('last_modified', sortable=True)
            ), stopwords=stopwords)

            # Iterate module JSON files
            qconn = StrictRedis.from_url(queue_url)
            s = Scheduler(connection=qconn)
            for filename in os.listdir(self._directory):
                if filename.endswith(".json"): 
                    with open('{}/{}'.format(self._directory, filename)) as fp:
                        mod = json.load(fp)

                    # Store the module in the database
                    docId = 'module:{}'.format(mod['name'])
                    m = RedisModule(self._conn, docId)
                    m.load(mod)

                    # Add a reference to it in the master catalog
                    self._conn.jsonset(self._key, Path('.modules["{}"]'.format(mod['name'])), 
                    {
                        'id': m.docId,
                        'created_timestamp': timestamp.isoformat(),
                    })

                    # Schedule a job to refresh repository statistics, starting from now and every 4 hours
                    s.schedule(
                        scheduled_time=timestamp,
                        func=callUpateStats,
                        args=[db_url, docId, ghlogin_or_token],
                        interval=60*60*4,
                        repeat=None,
                        ttl=0,
                        result_ttl=0
                    )

    def getModules(self, query=None, sort=None):
        if not query:
            # Use a purely negative query to get all modules
            query = '-etaoinshrdlu'
        q = Query(query).no_content().paging(0, 1000)
        if sort:
            if sort == 'update':
                q.sort_by('last_modified')
            elif sort == 'stars':
                q.sort_by('stargazers_count', asc=False)
            elif sort == 'forks':
                q.sort_by('forks_count', asc=False)

        results = self._conn.search(q)
        p = self._conn.pipeline()
        for doc in results.docs:
            p.jsonget(doc.id)
        return {
            'modules': p.execute()
        }

        modules = self._conn.jsonget(self._key, Path('.modules'))
        p = self._conn.pipeline()
        for k, v in modules.iteritems():
            p.jsonget(v['id'])
        return {
            'modules': p.execute()
        }

    def getSearchSuggestions(self, prefix):
        suggestions = self._conn.get_suggestions(prefix)
        return [s.string for s in suggestions]

    def getSearchResults(self, query):
        results = self._conn.search(query)
        p = self._conn.pipeline()
        for doc in results.docs:
            p.jsonget(doc.id)
        return {
            'modules': p.execute()
        }