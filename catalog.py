import hashlib
import json
import logging
import os
import time

from redismodule import RedisModule
from redisearchjson import Client, NumericField, Path, TextField

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class Catalog(object):

    _conn = None
    _key = 'hub:catalog'

    def __init__(self):
        epoch = int(time.time())
        logger.info('Initializing modules catalog')

        with open('modules.json') as fp:
            mods = json.load(fp)

        sha1 = hashlib.sha1(json.dumps(mods)).hexdigest()

        self._conn = Client(os.environ['REDIS_URL'], 'idx')

        # Check if catalog exists
        if self._conn.exists(self._key):
            if self._conn.jsonget(self._key, Path('.jsonfile_sha1')) == sha1:
                logger.info('No changes detected in modules file')
                pass
            else:
                logger.info('New modules file detected - TBD merge?!? ')
                pass
        else:   # Create the catalog
            logger.info('Building catalog in Redis')
            # Store the master catalog as an object
            self._conn.jsonset(self._key, Path.rootPath(),
            {
                'created_timestamp': epoch,
                'jsonfile_sha1': sha1,
                'modules': {},
            })

            # Create an index for the modules
            self._conn.create_index((
                TextField('name'),
                TextField('description'),
                NumericField('stargazers_count', sortable=True),
                NumericField('forks_count', sortable=True),
            ), stopwords = ('redis', 'module'))

            for mod in mods:
                # Create the module
                m = RedisModule('module:{}'.format(mod['name']), mod=mod, conn=self._conn)

                # Add a reference to it in the catalog
                self._conn.jsonset(self._key, Path('.modules["{}"]'.format(mod['name'])), 
                {
                    'id': m.docId,
                    'created_timestamp': epoch,
                })

    def getAllModules(self):
        modules = self._conn.jsonget(self._key, Path('.modules'))
        p = self._conn.pipeline()
        for k, v in modules.iteritems():
            p.jsonget(v['id'])
        return p.execute()