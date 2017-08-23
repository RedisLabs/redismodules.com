import hashlib
import json
import logging
import os
import re
from datetime import datetime

from dotenv import find_dotenv, load_dotenv
from github import Github, InputGitTreeElement, enable_console_debug_logging, UnknownObjectException
from redis import ConnectionPool, Redis, StrictRedis
from redisearch import Client as RediSearchClient
from redisearch import (AutoCompleter, NumericField, Query, SortbyField,
                        Suggestion, TextField)
from rejson import Client as ReJSONClient
from rejson import Path
from rq import Queue
from rq_scheduler import Scheduler

from stopwords import stopwords

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

load_dotenv(find_dotenv())

# TODO:
# * Interactions with gh fail on SSL, timeouts... - need to devise a way to deal w/ that

def _durationms(func, *args, **kwargs):
    start = datetime.now()
    res = func(*args, **kwargs)
    return res, (datetime.now() - start).total_seconds() * 1000.0

def _toepoch(ts):
    return (ts - datetime(1970,1,1)).total_seconds()

class Hub(object):
    dconn = None   # document store connection
    sconn = None   # search index connection
    qconn = None   # queue connection
    gh = None
    autocomplete = None
    _ts = None
    _hubkey = 'hub:catalog'
    _ixname = 'ix'
    _acname = 'ac'

    def __init__(self, ghlogin_or_token=None, docs_url=None, search_url=None, queue_url=None):
        timestamp = datetime.utcnow()
        logger.info('Initializing temporary hub {}'.format(timestamp))

        if ghlogin_or_token:
            self.gh = Github(ghlogin_or_token)
        elif 'GITHUB_TOKEN' in os.environ:
            self.gh = Github(os.environ['GITHUB_TOKEN'])
        else:
            logger.info('Env var ''GITHUB_TOKEN'' not found')

        if docs_url:
            pass
        elif 'DOCS_REDIS_URL' in os.environ:
            docs_url = os.environ['DOCS_REDIS_URL']
        else:
            logger.critical('No Redis for document storage... bye bye.')
            raise RuntimeError('No Redis for document storage... bye bye.')
        self.dconn = ReJSONClient().from_url(docs_url)

        if search_url:
            pass
        elif 'SEARCH_REDIS_URL' in os.environ:
            search_url = os.environ['SEARCH_REDIS_URL']
        else:
            search_url = docs_url
        conn = Redis(connection_pool=ConnectionPool().from_url(search_url))
        self.sconn = RediSearchClient(self._ixname, conn=conn)
        self.autocomplete = AutoCompleter(self._acname, conn=conn)

        if queue_url:
            pass
        elif 'QUEUE_REDIS_URL' in os.environ:
            queue_url = os.environ['QUEUE_REDIS_URL']
        else:
            queue_url = docs_url
        self.qconn = StrictRedis.from_url(queue_url)

        # Check if hub exists
        if self.dconn.exists(self._hubkey):
            self._ts = datetime.fromtimestamp(float(self.dconn.jsonget(self._hubkey, Path('.created'))))
            logger.info('Latching to hub {}'.format(self._ts))
        else:
            self._ts = timestamp
            logger.info('Creating hub {}'.format(self._ts))
            self.createHub()
            self.addModulesRepo(os.environ['REDISMODULES_REPO'])

    def createHub(self):
        logger.info('Creating the hub in the database {}'.format(self._ts))
        # Store the master modules catalog as an object
        self.dconn.jsonset(self._hubkey, Path.rootPath(),
        {
            'created': str(_toepoch(self._ts)),
            'modules': {},
            'submissions': {},
            'submitfails': [],
        })

        # Create a RediSearch index for the modules
        # TODO: catch errors
        self.sconn.create_index((
            TextField('name', sortable=True),
            TextField('description'),
            NumericField('stargazers_count', sortable=True),
            NumericField('forks_count', sortable=True),
            NumericField('last_modified', sortable=True)
        ), stopwords=stopwords)

    def deleteHub(self):
        # TODO
        pass

    def addModule(self, mod):
        logger.info('Adding module to hub {}'.format(mod['name']))
        # Store the module object as a document
        m = RedisModule(self, mod['name'])
        m.load(mod)

        # Add a reference to it in the master catalog
        self.dconn.jsonset(self._hubkey, Path('.modules["{}"]'.format(mod['name'])), 
        {
            'id': m.docId,
            'key': m.docKey,
            'created': str(_toepoch(self._ts)),
        })

        # Schedule a job to refresh repository statistics, starting from now and every 4 hours
        s = Scheduler(connection=self.qconn)
        job = s.schedule(
            scheduled_time=self._ts,
            func=callRedisModuleUpateStats,
            args=[m.docId],
            interval=60*60,     # every hour hours
            repeat=None,        # indefinitely
            ttl=0,
            result_ttl=0
        )
        return m

    """
    Adds modules to the hub from a local directory
    TODO: deprecate
    """
    def addModulesPath(self, path):
        logger.info('Loading modules from local path {}'.format(path))
        # Iterate module JSON files
        for filename in os.listdir(path):
            if filename.endswith(".json"): 
                with open('{}/{}'.format(path, filename)) as fp:
                    mod = json.load(fp)

                m = self.addModule(mod['name'], mod)

    """
    Adds a modules to the hub from a github repository
    """
    def addModulesRepo(self, name, path='/modules/'):
        # TODO: check for success
        q = Queue(connection=self.qconn)
        q.enqueue(callLoadModulesFromRepo, name, path)

    def loadModulesFromRepo(self, name, path):
        logger.info('Loading modules from Github {} {}'.format(name, path))
        # TODO: error handling, sometimes not all contents are imported?
        repo = self.gh.get_repo(name)
        files = repo.get_dir_contents(path)
        for f in files:
            mod = json.loads(f.decoded_content)
            m = self.addModule(mod)

    """
    Submits a module to the hub
    """
    def submitModule(self, repo_id, author=None, icon_url=None):
        logger.info('Module submitted to hub {}'.format(repo_id))
        ts = datetime.utcnow()
        res = {
            'status': 'failed'
        }

        # Check if the module is already listed
        if self.dconn.jsontype(self._hubkey, Path('.modules["{}"]'.format(repo_id))):
            res['message'] = 'Module already listed in the hub'
            return res

        # Check if there's an active submission, or if the failure was too recent
        # TODO: need a way to return None if Response is key doesn't exist
        if self.dconn.jsontype(self._hubkey, Path('.submissions["{}"]'.format(repo_id))):
            submission = self.dconn.jsonget(self._hubkey, Path('.submissions["{}"]'.format(repo_id)))
            if submission['status'] != 'failed':
                res['message'] = 'Module already submitted to the hub'
                return res
            else:
                # TODO: transactionalize
                self.dconn.jsonarrappend(self._hubkey, Path('.submitfails'), submission)
                self.dconn.jsondel(self._hubkey, Path('.submissions["{}"]'.format(repo_id)))

        # Store the new submission in a sub document
        submission = {
            'created': _toepoch(ts),
            'id': repo_id,
            'status': 'queued',
            'details': {
                'name': repo_id.split('/')[1],
                'repository': repo_id,
                'authors': [ author ],
                'icon_url': icon_url,
            }
        }
        # TODO: should be transactionalized?
        self.dconn.jsonset(self._hubkey, Path('.submissions["{}"]'.format(repo_id)), submission)

        # Add a job to process the submission
        q = Queue(connection=self.qconn)
        job = q.enqueue(callProcessModuleSubmission, repo_id)
        if job is None:
            res['message'] = 'Submission job could not be created'
            # TODO: design retry path
            logger.error('Could not create submission processing job for {}'.format(repo_id))
        else:
            res['status'] = 'queued'
            res['jobid'] = str(job.id)
        return res

    def getSubmissionStatus(self, jobid):
        q = Queue(connection=self.qconn)
        job = q.fetch_job(jobid)
        res = {
            'status': None,
            'jobid': jobid
        }
        if job is None:
            res['status'] = 'failed'
            res['message'] = 'Submission job not found'
        elif job.is_queued:
            res['status'] = 'queued'
        elif job.is_started:
            res['status'] = 'started'
        elif job.is_failed:
            res['status'] = 'failed'
            res['message'] = 'Submission job had failed'
        elif job.is_finished:
            repo_id = job.args[0]
            submission = self.dconn.jsonget(self._hubkey, Path('.submissions["{}"]'.format(repo_id)))
            res['status'] = submission['status']
            if 'finished' == res['status']:
                res['commit'] = submission['commit']
                res['pull'] = submission['pull']
                res['url'] = 'https://github.com/{}/pulls/{}'.format(os.environ['REDISMODULES_REPO'], submission['pull'])
            else:
                res['status'] = 'failed'
                res['message'] = submission['error']

        return res

    def processModuleSubmission(self, repo_id):
        logger.info('Processing submision for {}'.format(repo_id))
        # TODO: refactor into RedisModule
        # TODO: should this be broken to littler steps?
        self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].status'.format(repo_id)), 'started')
        submission = self.dconn.jsonget(self._hubkey, Path('.submissions["{}"]'.format(repo_id)))

        # TODO: try to validate submission a litle more
        try:
            subrepo = self.gh.get_repo(repo_id)
            description = subrepo.description or 'This module has an air of mystery about it' 
        except UnknownObjectException:
            self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].status'.format(repo_id)), 'failed')
            self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].error'.format(repo_id)), 'Repository not found on Github')
            return

        # TODO: move this to using RedisModule class
        mod = {
            'name': repo_id.split('/')[1],
            'license': None,
            'repository': {
                'type': 'github',
                'id': repo_id,
                'url': 'https://github.com/{}'.format(repo_id)
            },
            'documentation': None,
            'description': description,
            'authors': []
        }

        # Validate authors
        # TODO: currenty only gh
        authors = submission['details']['authors']
        for author in authors:
            try:
                ghauthor = self.gh.get_user(author)
            except UnknownObjectException:
                self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].status'.format(repo_id)), 'failed')
                self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].error'.format(repo_id)), 'Author {} not found on Github'.format(author))
                return
            mod['authors'].append({
                'type': 'github',
                'id': author,
                'url': 'https://github.com/{}'.format(author)
            })

        # TODO: validate and try to bring the icon from url and/or file upload
        if submission['details']['icon_url']:
            mod['icon'] = submission['details']['icon_url']

        # Submit to Github as a pull request
        ghrepo = self.gh.get_repo(os.environ['REDISMODULES_REPO'])
        ghdefault = ghrepo.get_branch(ghrepo.default_branch)

        # Get the branch for the submission
        try:
            ghsubref = ghrepo.get_git_ref('heads/submissions/{}'.format(repo_id))
        except UnknownObjectException:
            ghsubref = None

        # Create it if it doesn't exist
        if not ghsubref or not ghsubref.ref:
            ghsubref = ghrepo.create_git_ref('refs/heads/submissions/{}'.format(repo_id), ghdefault.commit.sha)

        ghsub = ghrepo.get_branch('submissions/{}'.format(repo_id))
        parent = ghrepo.get_git_commit(ghsub.commit.sha)

        # Create a new tree from the existing reference
        # TODO: add the icon if fetchable & suitable
        currtree = ghrepo.get_git_tree(ghsub.commit.sha)
        jsonfile = json.dumps(mod, indent=4, separators=(',', ': '))
        elems = [
            InputGitTreeElement('modules/{}.json'.format(submission['details']['name']), '100644', 'blob', content=jsonfile),
        ]
        tree = ghrepo.create_git_tree(elems, base_tree=currtree)

        # Fetch the existing pull request, if it does
        pr = None
        for pull in ghrepo.get_pulls(head=ghsub.name):
            # TODO: is it safe to assume 0 or 1?
            pr = pull

        # Commit the tree
        if pr:
            message = 'Updates submission'
        else:
            message = 'Initial submission of module {}'.format(repo_id)
        commit = ghrepo.create_git_commit(message, tree, [parent])
        self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].commit'.format(repo_id)), commit.sha)

        # Update the submission's reference
        # TODO: resolve why this isn't a fast forward
        ghsubref.edit(commit.sha, force=True)

        # Create a PR if it doesn't exist already
        if not pr:
            # Prepare the body of the pull request
            body =  'This module has been submitted via the hub.\n\n'
            body += '#Owner: @{}\n'.format(subrepo.owner.login)

            if authors:
                body += 'Authors:'
                for author in mod['authors']:
                    body += ' @{}'.format(author['id'])
                body += '\n'

            # The pull request is created against the master branch
            prkw = {
                'title': '[SUBMISSION] {}'.format(repo_id),
                'body': body,
                'head': ghsub.name,
                'base': ghdefault.name,
            }
            pr = ghrepo.create_pull(**prkw)

        self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].pull'.format(repo_id)), pr.number)
        self.dconn.jsonset(self._hubkey, Path('.submissions["{}"].status'.format(repo_id)), 'finished')

        return pr.number

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
            elif sort == 'name':
                q.sort_by('name')

        results = self.sconn.search(q)
        p = self.dconn.pipeline()
        mods = []
        for doc in results.docs:
            m = RedisModule(self, doc.id)
            mods.append(m.to_dict(pipeline=p))
        res, fetch_duration = _durationms(p.execute)

        return {
            'results': results.total,
            'search_duration': '{:.3f}'.format(results.duration),
            'fetch_duration': '{:.3f}'.format(fetch_duration),
            'total_duration': '{:.3f}'.format(fetch_duration + results.duration),
            'modules': mods,
        }

    def getSearchSuggestions(self, prefix):
        suggestions = self.autocomplete.get_suggestions(prefix)
        return [s.string for s in suggestions]

class Repository(object):
    data = None
    def __init__(self, idof, typeof, url):
        self.data = {
            'id': idof,
            'type': typeof,
            'url': url
        }

    def get_id(self):
        return self.data['id']

    def get(self):
        return self.data

class GithubRepository(Repository):
    def __init__(self, idof):
        Repository.__init__(self, idof, 'github', 'https://github.com/{}'.format(idof))

class Author(object):
    data = None
    def __init__(self, idof, typeof, url):
        self.data = {
            'id': idof,
            'type': typeof,
            'url': url
        }

    def get_id(self):
        if self.data:
            return self.data['id']
        else:
            return None

    def get(self):
        return self.data

class GithubAuthor(Author):
    def __init__(self, idof=None):
        if idof:
            Author.__init__(self, idof, 'github', 'https://github.com/{}'.format(idof))

class RedisModule(object):
    _hub = None
    docId = None
    docKey = None

    def __init__(self, hub, docId):
        self._hub = hub
        self.docId = docId
        self.docKey = 'module:{}'.format(docId)

    def exists(self):
        return self._hub.dconn.exists(self.docKey)

    def to_dict(self, pipeline=None):
        if pipeline:
            return pipeline.jsonget(self.docKey)
        else:
            return self._hub.dconn.jsonget(self.docKey)

    def load(self, mod):
        self.__init__(self._hub, mod['name'])
        # Store the module
        self._hub.dconn.jsonset(self.docKey, Path.rootPath(), mod)
        # Index it
        self._hub.sconn.add_document(self.docId, nosave=True,
            name=mod['name'],
            description=mod['description'], 
        )
        # Add the module's name and description to the suggestions engine
        text = '{} {}'.format(mod['name'], mod['description'])
        words = set(re.compile('\w+').findall(text))
        words = set(w.lower() for w in words)
        words = words.difference(stopwords)
        self._hub.autocomplete.add_suggestions(*[Suggestion(w) for w in words])

    def updateStats(self):
        # github.enable_console_debug_logging()
        mod = self._hub.dconn.jsonget(self.docKey, Path('name'), Path('description'), Path('repository'))
        repo = mod['repository']

        if repo and \
            'type' in repo and repo['type'] == 'github' and \
            'id' in repo:

            logger.info('Fetching stats for {}'.format(repo['id']))
            grepo = self._hub.gh.get_repo(repo['id'])
            stats = {
                'stargazers_count': grepo.stargazers_count,
                'forks_count': grepo.forks_count,
                'last_modified': (datetime.today() - grepo.pushed_at).days  # TODO: take last push from default branch
            }

            rel = grepo.get_releases()
            try:
                stats['last_release'] = {
                    'name': rel[0].tag_name,
                    'url': rel[0].url
                }
            except IndexError:
                pass

        self._hub.dconn.jsonset(self.docKey, Path('.stats'), stats)
        self._hub.sconn.add_document(self.docId, nosave=True, replace=True, name=mod['name'], description=mod['description'], **stats)

"""
Exported Functions
"""

def callRedisModuleUpateStats(docId):
    logger.info('Calling update stats for {}'.format(docId))
    hub = Hub()
    if hub.gh:
        module = RedisModule(hub, docId)
        module.updateStats()
    else:
        logger.error('No Github access for updating stats {}'.format(docId))

def callLoadModulesFromRepo(name, path):
    logger.info('Calling load modules from github {} {}'.format(name, path))
    hub = Hub()
    if hub.gh:
        hub.loadModulesFromRepo(name, path)
    else:
        logger.error('No Github access for loading {} {}'.format(name, path))

def callProcessModuleSubmission(repoid):
    logger.info('Calling process module submission {}'.format(repoid))
    hub = Hub()
    if hub.gh:
        hub.processModuleSubmission(repoid)
    else:
        logger.error('No Github access for processing submission {}'.format(repoid))
